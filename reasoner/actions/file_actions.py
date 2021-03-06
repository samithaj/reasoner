"""A set of actions based on stored files for offline access.
"""

from .action import Action
import pandas as pd
import os.path
import pickle

class FileSourcedAction(Action):

    def __init__(self, precondition, effect, source_file, column_map):
        assert len(column_map) == 1, 'FileSourcedAction only supports single effect'
        super().__init__(precondition, effect)
        self.source_file = source_file
        self.column_map = column_map
        self.precondition_columns = self.precondition_column_map(self.precondition_entities)
        #print(self.precondition_columns)
        assert len(self.precondition_columns) == len(self.precondition_entities), \
          'precondition_entities '+str(self.precondition_entities)+' not found among column_map values '+str(column_map)


    def precondition_column_map(self, precondition_entities):
        map = {}
        for spec in self.column_map:
            for column in self.column_map[spec]:
                if self.column_map[spec][column].get('precondition') in precondition_entities:
                    map[self.column_map[spec][column].get('precondition')] = column
        return map


    def row_to_entry(self, row):
        entries = {}
        for spec in self.column_map:
            entry = {'node':{},'edge':{}}
            for column in self.column_map[spec]:
                key_dict = self.column_map[spec][column]
                for key in key_dict:
                    if key == 'node_value':
                        for value_key in key_dict[key]:
                            entry['node'][value_key] = key_dict[key][value_key]
                    if key == 'edge_value':
                        for value_key in key_dict[key]:
                            entry['edge'][value_key] = key_dict[key][value_key]
                    if key == 'node' or key == 'edge':
                        entry[key][key_dict[key]] = row[column]
            entries[spec] = [entry]
        return entries


    def execute(self, input):
        res = []
        df = self.read_file()
        for index, row in df.iterrows():
            if self.match(row, input):
                res.append(self.row_to_entry(row))
        return res


    def match(self, row, input):
        for key in input:
            if row[self.precondition_columns[key]].lower() != input[key].lower():
                return False
        return True


    def read_file(self):
        df = pd.read_csv(self.source_file,sep='\t',keep_default_na=False)
        print('Read '+str(len(df))+' lines: '+self.source_file)
        return df


class CachedFileSourcedAction(FileSourcedAction):

    def __init__(self, precondition, effect, source_file, column_map):
        super().__init__(precondition, effect, source_file, column_map)
        self.load_file(source_file)


    def load_file(self, filename):
        pickle_file = os.path.dirname(filename) + '/' + self.__class__.__name__ + '.pickle'
        if os.path.isfile(pickle_file):
            with open(pickle_file, 'rb') as f:
                self.input = pickle.load(f)
                print('Loaded from '+pickle_file)
        else:
            self.input = self.parse_input_file(self.read_file())
            with open(pickle_file, 'wb') as f:
                pickle.dump(self.input, f)
                print('Saved to '+pickle_file)

    def parse_input_file(self, input):
        input_map = {}
        for index, row in input.iterrows():
            map = input_map
            for entity in sorted(self.precondition_entities):
                key = row[self.precondition_columns[entity]].lower()
                if key not in map:
                    map[key]={}
                map = map[key]
            if 'list' not in map:
                map['list']=[]
            map['list'].append(self.row_to_entry(row))
        return input_map


    def execute(self, input):
        map = self.input
        for entity in sorted(self.precondition_entities):
            if input[entity].lower() not in map:
                return []
            map=map[input[entity].lower()]
        return map['list']


class DrugBankDrugToTarget(CachedFileSourcedAction):
    """Use DrugBank to find targets for a drug (returns human genes).
    """
    def __init__(self, filename='./data/drugbank.txt'):
        column_map = { 'Target': {
            'Name': {'precondition':'Drug'},
            'Action': {'edge':'action'},
            'TargetID': {'node':'id'},
            'Symbol': {'node':'name'},
            'HGNC': {'node':'HGNC'},
            '+1': {'node_value': {'authority':'DrugBank:TargetID'}}
        }}
        super().__init__(['bound(Drug)'],['bound(Target) and connected(Drug, Target)'], filename, column_map)


class DrugBankDrugToUniProtTarget(CachedFileSourcedAction):
    """Use DrugBank to find targets for a drug (returns proteins for any species).
    """
    def __init__(self, filename='./data/drugbankUniProt.txt'):
        column_map = { 'Target': {
            'Name': {'precondition':'Drug'},
            'Action': {'edge':'action'},
            'UniProt': {'node':'id'},
            'Target': {'node':'name'},
            '+1': {'node_value': {'authority':'UniProt'}}
        }}
        super().__init__(['bound(Drug)'],['bound(Target) and connected(Drug, Target)'], filename, column_map)


class GoFunctionTargetToPathway(CachedFileSourcedAction):
    """Use GeneOntology molecular functions to find pathways for a target.
    """
    def __init__(self, filename='./data/GO_function.txt'):
        column_map = { 'Pathway': {
            'Symbol': {'precondition':'Target'},
            'GOID': {'node':'id'},
            'GOTerm': {'node':'name'},
            'GOEvidenceCode': {'edge':'GOEvidenceCode'},
            '+1': {'node_value': {'authority':'GO'}}
        }}
        super().__init__(['bound(Target)'],['bound(Pathway) and connected(Target, Pathway)'], filename, column_map)


class GoProcessTargetToPathway(CachedFileSourcedAction):
    """Use GeneOntology processes to find pathways for a target.
    """
    def __init__(self, filename='./data/GO_process.txt'):
        column_map = { 'Pathway': {
            'Symbol': {'precondition':'Target'},
            'GOID': {'node':'id'},
            'GOTerm': {'node':'name'},
            'GOEvidenceCode': {'edge':'GOEvidenceCode'},
            '+1': {'node_value': {'authority':'GO'}}
        }}
        super().__init__(['bound(Target)'],['bound(Pathway) and connected(Target, Pathway)'], filename, column_map)


class MeshScopeNoteDiseaseToSymptom(CachedFileSourcedAction):
    """Use MeSH scope notes to find symptoms for a disease.
    """
    def __init__(self, filename='./data/MeshScopeNote.txt'):
        column_map = { 'Symptom': {
            'MeSH_term': {'precondition':'Disease'},
            'scopeNote_term': {'node':'scopeNote'},
            'scopeNote_MeshTerm': {'node':'name'}
        }}
        super().__init__(['bound(Disease)'],['bound(Symptom) and connected(Disease, Symptom)'], filename, column_map)


class CellOntologyTargetAndCellToPathway(CachedFileSourcedAction):
    """Use CellOntology to find pathways given a target and cell.
    """
    def __init__(self, filename='./data/cellOntology2GO.txt'):
        column_map = {'Pathway':{
            'Symbol': {'precondition': 'Target'},
            'name': {'precondition': 'Cell'},
            'qualifier': {'edge': 'qualifier'},
            'GOID': {'node':'id'},
            'GOTerm': {'node':'name'},
            '+1': {'node_value': {'authority':'GO'}}
        }}
        super().__init__(['bound(Target)','bound(Cell)'],['bound(Pathway) and connected(Pathway, Target) and connected(Pathway, Cell)'], filename, column_map)


class CellOntologyTargetAndPathwayToCell(CachedFileSourcedAction):
    """Use CellOntology to find cells given a target and pathway.
    """
    def __init__(self, filename='./data/cellOntology2GO.txt'):
        column_map = {'Cell':{
            'Symbol': {'precondition': 'Target'},
            'GOTerm': {'precondition': 'Pathway'},
            'qualifier': {'edge': 'qualifier'},
            'CLID': {'node':'id'},
            'name': {'node':'name'},
            '+1': {'node_value': {'authority':'CellOntology'}}
        }}
        super().__init__(['bound(Target)','bound(Pathway)'],['bound(Cell) and connected(Pathway, Target) and connected(Pathway, Cell)'], filename, column_map)


class DskdDiseaseToSymptom(CachedFileSourcedAction):
    """Use Disease Symptom Knowledge DB to find symptoms given a disease.
    """
    def __init__(self, filename='./data/DiseaseSymptomKnowledgeDatabase.txt'):
        column_map = { 'Symptom': {
            'disease_name': {'precondition':'Disease'},
            'symptom_id': {'node':'id'},
            'symptom_name': {'node':'name'},
            '+1': {'node_value': {'authority':'UMLS'}}
        }}
        super().__init__(['bound(Disease)'],['bound(Symptom) and connected(Disease, Symptom)'], filename, column_map)
