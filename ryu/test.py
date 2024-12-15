# -*- coding: utf-8 -*-
"""
@File     : test.py
@Date     : 2022-07-20 16:06
@Author   : Terry_Li  - 既然选择了远方，便只顾风雨兼程。
IDE       : PyCharm
@Mail     : 1419727833@qq.com
"""
import networkx as nx
# 定义图的节点和边
from matplotlib import pyplot as plt

# 定义graph
G = nx.path_graph(4, create_using=nx.DiGraph())
G.add_path([7, 8, 3])
G.add_path([5, 6, 9])

# 找出所有的弱连通图
for c in nx.weakly_connected_components(G):
    print(c)

# 由大到小的规模判断弱连通子图
print([len(c) for c in sorted(nx.weakly_connected_components(G), key=len, reverse=True)])

nx.draw(G, with_labels=True, font_weight='bold')
plt.axis('on')
plt.xticks([])
plt.yticks([])
plt.show()