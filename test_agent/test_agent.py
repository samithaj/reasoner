import pandas
from reasoner.KGAgent import KGAgent

agent = KGAgent()

# agent.cop_query('C0909381', 'C0206178')
# graph = agent.get_graph()

# print(graph.nodes(data=True))
# print(graph.edges(data=True))

cop_file = '../data/neo4j/cop_benchmark_input_cui_curated.csv'
cop = pandas.read_csv(cop_file)

for index, row in cop.iterrows():
    agent.cop_query(row['drug_cui'], row['disease_cui'])
    for record in  agent.get_result():
        print(record)
