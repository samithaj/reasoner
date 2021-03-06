import numpy
import scipy
import mdptoolbox
from collections import OrderedDict
from .actions.action import Action

class Noop(Action):
    # A default action to indicate all goal-oriented actions have been tried.
    def __init__(self):
        super().__init__([], [])

class Success(Action):
    # Action associated with the goal state.
    #
    # The `Success` action is used to orient the agent towards the goal state.
    # It will be associated with a high reward upon initialization and can
    # only be executed in a goal state.
    def __init__(self, goal_state):
        super().__init__(goal_state, [])


class ActionPlanner:
    """
    Find a plan for reaching a goal state from the current state.
    
    Given a set of actions (a ``KnowledgeMap``) and a goal state, the ``ActionPlanner``
    class uses a Markov decision process (MDP) to plan a strategy for knowledge acquisition.
    It calculates the MDP policy using a value iteration algorithm and provides an interface
    to getting the best action for a specific state, marking actions as used, and replanning
    if the original plan failed.
    

    Parameters
    ----------
    
    knowledge_map : ~reasoner.KnowledgeMap.KnowledgeMap
       The ``KnowledgeMap`` used for planning.
       
    goal_state : dict
       A dictionary of state variables that represent a goal state.
       
    default_reward : numeric
        A default reward; assigned to all states that do not satisfy
        an action's preconditions.

    """
    def __init__(self, knowledge_map, goal_state, default_reward = -2):
        self.knowledge_map = knowledge_map
        self.state_variable_map = dict()
        self.state_variables = [self.get_canonical_state_variable(x) for x in knowledge_map.state_variables]
        self.actions = knowledge_map.actions.copy()
        self.actions.insert(0, {
            'action':Noop(),
            'p_success':0,
            'reward':-1
        })
        self.actions.append({
          'action':Success(goal_state),
          'p_success':0,
          'reward':5
        })

        for action in self.actions:
            action['action'].precondition = [self.get_canonical_state_variable(x) for x in action['action'].precondition]
            action['action'].effect_terms = [self.get_canonical_state_variable(x) for x in action['action'].effect_terms]
            tmp_constraint_list = list()
            for constraint in action['action'].effect_constraints:
                tmp_constraint = list()
                for term in constraint:
                    tmp_constraint.append(self.get_canonical_state_variable(term))
                tmp_constraint_list.append(tuple(tmp_constraint))
            action['action'].effect_constraints = tmp_constraint_list

        self.goal_state = [self.get_canonical_state_variable(x) for x in goal_state]
        self.action_names = [type(x['action']).__name__ for x in self.actions]
        self.action_repository = tuple(self.actions)
        self.actions_used = list()

        self.default_reward = default_reward
        self.plan = None
        self.__set_pr()

    def canonicalize_state_variable(self, variable):
        if 'connected(' in variable:
            sorted_list = sorted([x.strip() for x in variable[10:-1].split(',')])
            canonical = 'connected(' + ', '.join(sorted_list) + ')'
            return(canonical)
        else:
            return(variable)

    def get_canonical_state_variable(self, variable):
        if variable not in self.state_variable_map:
            self.state_variable_map[variable] = self.canonicalize_state_variable(variable)
        return(self.state_variable_map[variable])

    def __get_bitlist(self, var_list):
        return([x in var_list for x in self.state_variables])

    def __get_state_index(self, var_list):
        bitlist = [x in var_list for x in self.state_variables]
        return(self.__bit2idx(bitlist))

    def __bit2idx(self, bitlist):
        return(sum(1<<i for i, b in enumerate(bitlist) if b))

    def __all_matches(self, bitlist, index = 0):
        """Given a bit pattern (list of True, False, or None for each bit),
        enumerate all bit strings that match the pattern
        where None indicates the wildcard (can be True or False)"""
        if (index == len(bitlist)):
            return [bitlist]

        if (bitlist[index] is None):
            tmp_a = bitlist.copy()
            tmp_a[index] = False
            a = self.__all_matches(tmp_a, index + 1)

            tmp_b = bitlist.copy()
            tmp_b[index] = True
            b = self.__all_matches(tmp_b, index + 1)
            l = a + b
        else:
            l = self.__all_matches(bitlist, index + 1)
        return(l)

    def __get_matching_states(self, var_list):
        matches = self.__all_matches(self.__get_bitlist(var_list))
        return({self.__bit2idx(x) for x in matches})

    def __get_pattern(self, true_list, false_list):
        """Create a bit pattern based on two lists indicate which variables
        must be True (true_list) and which variable must be False (false_list).
        All otther state variables will be set to the wildcard (indicated by None)."""
        bitlist = [None] * len(self.state_variables)
        for i in range(len(self.state_variables)):
            if self.state_variables[i] in true_list:
                bitlist[i] = True
            elif self.state_variables[i] in false_list:
                bitlist[i] = False
        return(bitlist)

    def __get_effect_states(self, from_state_bitlist, effect_terms):
        query_state = from_state_bitlist.copy()
        for i in range(len(query_state)):
            if self.state_variables[i] in effect_terms and not query_state[i] == True:
                query_state[i] = None
        return(self.__all_matches(query_state))

    def __ismember(self, a, b):
        bind = {}
        for i, elt in enumerate(b):
            if elt not in bind:
                bind[elt] = i
        return [bind.get(itm, None) for itm in a]

    def __filter_effect_states(self, states, constraints):
        out_states = list()
        for state in states:
            concordant = True
            for c in constraints:
                variable_sum = sum([state[i] for i in self.__ismember(c, self.state_variables)])
                if (not variable_sum == len(c)) and (not variable_sum == 0):
                    concordant = False
                    break
            if concordant:
                out_states.append(state)
        return(out_states)

    def __get_action_from_to_states(self, action):
        precon_pattern = self.__get_pattern(action.precondition, [])
        from_state_bitlists = self.__all_matches(precon_pattern)
        state_dict = dict()
        for x in from_state_bitlists:
            from_state = self.__bit2idx(x)
            effect_bitlists = self.__get_effect_states(x, action.effect_terms)
            filtered_effect_bitlists = self.__filter_effect_states(effect_bitlists, action.effect_constraints)
            effect_states = {self.__bit2idx(s) for s in filtered_effect_bitlists}
            state_dict[from_state] = effect_states - {from_state}
        return(state_dict)

    def __set_pr(self):
        n_var = len(self.state_variables)
        n_actions = len(self.actions)
        n_states = pow(2, n_var)

        P = [scipy.sparse.lil_matrix((n_states, n_states)) for i in range(n_actions)]
        R = numpy.full([n_states, n_actions], self.default_reward)

        for i in range(n_actions):
            for j in range(n_states):
                P[i][j,j] = 1

        counter = 0
        for action in self.actions:
            state_dict = self.__get_action_from_to_states(action['action'])
            for from_state,to_states in state_dict.items():
                if len(to_states) > 0 or isinstance(action['action'], Success):
                    P[counter][from_state, from_state] = 1 - action['p_success']
                    R[from_state, counter] = action['reward']
                    for to_state in to_states:
                        P[counter][from_state, to_state] = action['p_success']/len(to_states)
            counter = counter + 1
        self.P = [m.tocsr() for m in P]
        self.R = R

    def make_plan(self, discount):
        """Develop an initial plan.
        
        Parameters
        ----------
        discount : float
            A discount used in the MDP value iteration algorithm. Must be in range [0,1].
        
        """
        vi = mdptoolbox.mdp.ValueIteration(self.P, self.R, discount)
        vi.run()
        self.plan = vi

    def replan(self, discount):
        """Modify an existing plan.
        
        Parameters
        ----------
        discount : float
            A discount used in the MDP value iteration algorithm. Must be in range [0,1].
        
        """
        self.actions = [a for a in self.actions if not a in self.actions_used]
        self.__set_pr()
        vi = mdptoolbox.mdp.ValueIteration(self.P, self.R, discount)
        vi.run()
        self.plan = vi
    
    def get_action(self, state):
        """Return the best action to execute in a given state.
        
        Parameters
        ----------
        state : list
            A list of state variables.
        
        Returns
        -------
        Action  
            An object of type ``Action`` that represents the best action
            for the input state.
        
        """
        canonical_state = [self.get_canonical_state_variable(x) for x in state]
        assert (all(variable in self.state_variables for variable in canonical_state)),'State variables not valid:' + str(canonical_state)
        action = self.actions[self.plan.policy[self.__get_state_index(canonical_state)]]
        return(action['action'])

    def set_action_used(self, action):
        """Mark an action as used.
        
        Parameters
        ----------
        action : Action
            The action that should be marked used.
        
        """
        self.actions_used.extend([x for x in self.actions if x['action'] == action])
        
    def was_action_used(self, action):
        """Check if an action was used.
        
        Parameters
        ----------
        action : Action
            The action in question.
        
        Returns
        -------
        bool
            `True` if the action has been used, `False` otherwise.
        
        """
        return any([action == x['action'] for x in self.actions_used])
  