'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI/mininet-wifi/generate_topo_wifi_test.py
Date: 2023-07-24 15:23:58
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




# √
def parse_wifi_xml_topology(topology_path):
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
    ap_location_list = []
    sta_location_list = []
    for child in topo_element.iter():
        # parse nodes
        if child.tag == 'node':
            node_id = int(child.get('id'))
            graph.add_node(node_id)
            # 解析AP和STA的坐标
            ap_location = str(child.find('locationap').get('coordinate'))
            sta_location = str(child.find('locationsta').get('coordinate'))
            # 添加进列表
            ap_location_list.append(ap_location)  
            sta_location_list.append(sta_location)
        # parse link
        elif child.tag == 'link':
            from_node = int(child.find('from').get('node'))
            to_node = int(child.find('to').get('node'))
            graph.add_edge(from_node, to_node)

    nodes_num = len(graph.nodes)
    edges_num = len(graph.edges)

    print('nodes: ', nodes_num, '\n', graph.nodes, '\n',
          'edges: ', edges_num, '\n', graph.edges , '\n'
          'ap_location_list  : \n' , ap_location_list , '\n' ,
          'sta_location  : \n',sta_location_list)
    return graph, nodes_num, edges_num , ap_location_list , sta_location_list

# √
def generate_ap_port(graph):
    # 返回每个 node 的边字典
    ap_port_dict = {}
    for node in graph.nodes:
        ap_port_dict.setdefault(node, list(range(graph.degree[node])))
    return ap_port_dict

def generate_host_port(graph):
    switch_port_dict = generate_ap_port(graph)
    host_p = 0
    for port in switch_port_dict.values():
        if len(port) > host_p:
            host_p = len(port)
    return host_p + 1

def generate_node_idx(graph):
    node_idx = {}
    for idx , node in enumerate(graph.nodes):
        node_idx[node]= idx+1
    return node_idx

def get_node_location(gragh):
    location = []
    for node in gragh.nodes:
        location.append((gragh.nodes.get(node)['Longitude'], gragh.nodes.get(node)['Latitude'], 0))
    return location

# √
def get_mininet_device(net, idx: list, device='sta'):
    """
    获得idx中mininet-wifi的实例, 如 sta1, sta2 ...;  ap1, ap2 ...
    :param net: mininet网络实例
    :param idx: 设备标号集合, list
    :param device: 设备名称 'h', 's'
    :return d: dict{idx: 设备mininet实例}
    """
    d = {}
    for i in idx:
        d.setdefault(i, net.get(f'{device}{i}'))

    return d


def net_sta_ping_others(net,sta_num):
    stations = net.stations
    for i,h in enumerate(stations):
        if i+1==sta_num:
            continue
        net.ping((stations[sta_num-1], h))


def cal_ap_distance(ap1_location, ap2_location):
    ap1_x, ap1_y, ap1_z = ap1_location.split(',')
    ap2_x, ap2_y, ap2_z = ap2_location.split(',')

    x = abs(int(ap1_x) - int(ap2_x))
    y = abs(int(ap1_y) - int(ap2_y))

    distance = pow(x**2+y**2, 0.5)

    return distance


def run_ip_add_default(hosts: dict):
    """
        运行 ip route add default via 192.168.0.x 命令
    """
    _cmd = 'ip route add default via 192.168.0.'
    for i, h in hosts.items():
        print(_cmd + str(i))
        h.cmd(_cmd + str(i))
    print("---> run ip add default complete")


def _test_cmd(devices: dict, my_cmd):
    for i, d in devices.items():
        d.cmd(my_cmd)
        print(f'exec {my_cmd}zzz{i}')





if __name__=='__main__':
    
    xml_topology_path = r'topologies/topology_1.xml' 
    xml_topology_path2 = r'topology-zoo/Sunet.gml' #Tinet   Arnes.gml   Sunet
    graph, nodes_num, edges_num, ap_location, sta_location = parse_wifi_xml_topology(xml_topology_path)
    G = networkx.read_gml(xml_topology_path2)

    # import matplotlib.pyplot as plt
    # plt.subplot()
    # networkx.draw_networkx(G,with_labels=True, font_weight="bold")
