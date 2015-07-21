from Node import Node

__author__ = 'Mathieu'
import AddressUtils
from pymongo import MongoClient, DESCENDING

class Network:
    def __init__(self, db_server, db_port,):
        self.max_batch_insert = 10000
        self.db_server = db_server
        self.db_port = db_port
        self.addr_utils = AddressUtils.Addressutils()
        self.nodes = {}
        self.next_node_id = 1
        self.address_registry = {}


    def check_integrity(self):
        addresses_repertory = []
        for node in self.nodes.values():
            addresses_repertory += node.addresses
        addresses_repertory = sorted(addresses_repertory)
        print("Nb addr : ",len(addresses_repertory))
        print("Nb nodes : ",len(self.nodes))
        for i in range(len(addresses_repertory)-1):
            if addresses_repertory[i] == addresses_repertory[i+1]:
                print("duplicate for addr :",addresses_repertory[i])
                raise Exception("Invalid Graph Consistancy: duplicates addresses")

    def chunks(self,l, n):
        n = max(1, n)
        return [l[i:i + n] for i in range(0, len(l), n)]

    def process_transaction_data(self,inputs, outputs):
        try:
            addresses_in = set(map(self.addr_utils.convert_hash160_to_addr,map(self.addr_utils.convert_public_key_to_hash160,inputs)))
            addresses_out = list(map(lambda  x : self.addr_utils.get_hash160_from_CScript(x.scriptPubKey),outputs))
            assert(len(addresses_out) > 0)
        except Exception:
            #print("Unable to parse Tx : %s" %  repr(outputs))
            return

        new_node_addresses = []
        destination_node_id = -1
        for address in addresses_in:
            if address in self.address_registry:
                current_node_id = self.address_registry[address]
                if current_node_id == destination_node_id : continue;
                if destination_node_id >= 0:
                    self.nodes[destination_node_id].merge(self.address_registry,self.nodes,self.nodes[current_node_id])
                else:
                    destination_node_id = current_node_id
            else:
                new_node_addresses.append(address)

        if destination_node_id < 0:
            destination_node_id = self.next_node_id
            node = Node(destination_node_id)
            self.nodes[destination_node_id] = node
            self.next_node_id +=1

        self.nodes[destination_node_id].add_new_unique_adddresses(self.address_registry,new_node_addresses)


    def synchronize_mongo_db(self):
        client = MongoClient(self.db_server, self.db_port)
        db = client.bitcoin
        collection = db.addresses
        db_next_node_id = 1
        for x in collection.find().sort("n_id",DESCENDING).limit(1):
            db_next_node_id = x['n_id'] +1

        for node in self.nodes.values():

            existing_addresses = set()
            distinct_nodes_id = set()

            for addr in self.chunks(node.addresses,self.max_batch_insert):
                addresses_nodes = collection.find({"_id": {'$in':addr}})

                for x in addresses_nodes:
                    existing_addresses.add(x['_id'])
                    distinct_nodes_id.add(x['n_id'])

            merge_node_id = -1;
            if len(existing_addresses) > 0:
                min_node_id = min(distinct_nodes_id)
                merge_node_id = min_node_id
                if len(distinct_nodes_id) > 1:
                    distinct_nodes_id.remove(merge_node_id)
                    collection.update_many({'n_id':{'$in':[x for x in distinct_nodes_id]}}, {'$set':{'n_id':merge_node_id}})

            else:
                merge_node_id = db_next_node_id
                db_next_node_id +=1

            to_insert = [{'_id':x,'n_id':merge_node_id} for x in (set(node.addresses) - existing_addresses)]
            if len(to_insert) > 0:
                collection.insert_many(to_insert)

        client.close()
        print("DB Sync Finished")