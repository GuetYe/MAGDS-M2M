'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN_Practise/mininet/test_topo.py
Date: 2023-06-07 10:33:51
Description: 
'''

import os
import sys
curr_path=os.path.dirname(os.path.abspath(__file__)) # =sys.path[0]也可以
parent_path=os.path.dirname(curr_path)
sys.path.append(parent_path)

os.chdir(sys.path[0])
# print("\n",os.getcwd())

import time


import xml.etree.ElementTree as ET
import networkx




def parse_xml_topology(topology_path):
    """
    parse topology from topology.xml
    :return: topology graph, networkx.Graph()
             nodes_num,  int
             edges_num, int
    """
    tree = ET.parse(topology_path)
    root = tree.getroot()
    topo_element = root.find("topology")
    graph = networkx.Graph()
    for child in topo_element.iter():
        # parse nodes
        if child.tag == 'node':
            node_id = int(child.get('id'))
            graph.add_node(node_id)
        # parse link
        elif child.tag == 'link':
            from_node = int(child.find('from').get('node'))
            to_node = int(child.find('to').get('node'))
            graph.add_edge(from_node, to_node)

    nodes_num = len(graph.nodes)
    edges_num = len(graph.edges)

    print('nodes: ', nodes_num, '\n', graph.nodes, '\n',
          'edges: ', edges_num, '\n', graph.edges)
    return graph, nodes_num, edges_num


def generate_switch_port(graph):
    # 返回每个 node 的边字典
    switch_port_dict = {}
    for node in graph.nodes:
        switch_port_dict.setdefault(node, list(range(graph.degree[node])))
    return switch_port_dict


def get_mininet_device(net, idx: list, device='h'):
    """
        获得idx中mininet的实例, 如 h1, h2 ...;  s1, s2 ...
    :param net: mininet网络实例
    :param idx: 设备标号集合, list
    :param device: 设备名称 'h', 's'
    :return d: dict{idx: 设备mininet实例}
    """
    d = {}
    for i in idx:
        d.setdefault(i, net.get(f'{device}{i}'))

    return d


def net_h_ping_others(net,host_num):
    hosts = net.hosts
    for i,h in enumerate(hosts):
        if i+1==host_num:
            continue
        net.ping((hosts[host_num-1], h))


def run_ip_add_default(hosts: dict):
    """
        运行 ip route add default via 10.0.0.x 命令
    """
    _cmd = 'ip route add default via 10.0.0.'
    for i, h in hosts.items():
        print(_cmd + str(i))
        h.cmd(_cmd + str(i))
    print("---> run ip add default complete")











if __name__=='__main__':
    xml_topology_path = r'./topologies/topo.xml'
    graph, nodes_num, edges_num = parse_xml_topology(xml_topology_path)
