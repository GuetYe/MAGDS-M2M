'''
Author: J1HA0
Email: zhengjihao77@163.com
FilePath: /SDN-WIFI/rl/sac.py
Date: 2024-03-04 21:31:28
Description: 
'''

import sys
import os
import datetime
curr_path = os.path.dirname(os.path.abspath(__file__))  # 当前文件所在绝对路径
parent_path = os.path.dirname(curr_path)  # 父路径
sys.path.append(parent_path)  # 添加路径到系统路径
curr_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")  # 获取当前时间


import random
import numpy as np

import collections

import torch
import torch.nn.functional as F
from torch.distributions import Normal



class SAC_Config:
    def __init__(self) -> None:
        #-------------------------------- 环境超参数 --------------------------------
        self.env_name = 'Segment Route'
        self.algo_name= 'SAC'
        self.device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
        self.seed = 10 # 随机种子，置0则不设置随机种子
        #-----------------------------------------------------------------------------

        #-------------------------------- 算法超参数 --------------------------------
        self.gamma = 0.98
        self.actor_lr = 1e-4
        self.critic_lr = 1e-3
        self.alpha_lr = 1e-3
        self.buffer_size = 10000
        self.minimal_size = 2000
        self.batch_size = 32
        self.tau = 0.005  # 软更新参数
        self.target_entropy = -1
        #-----------------------------------------------------------------------------

        #-------------------------------- 训练调整 --------------------------------
        self.train_eps = 1000
        self.test_eps = 50
        #-----------------------------------------------------------------------------


        #-------------------------------- 保存结果相关参数  --------------------------------
        self.save = True # 是否保存图片
        # 保存结果相关参数 
        self.result_path = curr_path+"/outputs/" + self.env_name + \
            '/'+curr_time+'/results/'  # 保存结果的路径
        self.model_path = curr_path+"/outputs/" + self.env_name + \
            '/'+curr_time+'/models/'  # 保存模型的路径
        self.save = True # 是否保存图片

class PolicyNet(torch.nn.Module):
    def __init__(self, state_dim, hidden_dim, action_dim):
        super(PolicyNet, self).__init__()
        self.fc1 = torch.nn.Linear(state_dim, hidden_dim)
        self.fc2 = torch.nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = torch.nn.Linear(hidden_dim, action_dim)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return F.softmax(self.fc3(x), dim=1)

class QValueNet(torch.nn.Module):
    ''' 只有一层隐藏层的Q网络 '''
    def __init__(self, state_dim, hidden_dim, action_dim):
        super(QValueNet, self).__init__()
        self.fc1 = torch.nn.Linear(state_dim, hidden_dim)
        self.fc2 = torch.nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = torch.nn.Linear(hidden_dim, action_dim)

    def forward(self, x):
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc3(x)

class SAC:
    ''' 处理离散动作的SAC算法 '''
    def __init__(self, state_dim, hidden_dim, action_dim, cfg):
        # 经验回放
        self.memory = ReplayBuffer(cfg.buffer_size) 
        # her 经验池
        self.replay_buffer = ReplayBuffer_Trajectory(cfg.buffer_size) 
        # 策略网络
        self.actor = PolicyNet(state_dim, hidden_dim, action_dim).to(cfg.device)
        # 第一个Q网络
        self.critic_1 = QValueNet(state_dim, hidden_dim, action_dim).to(cfg.device)
        # 第二个Q网络
        self.critic_2 = QValueNet(state_dim, hidden_dim, action_dim).to(cfg.device)
        # 第一个目标Q网络
        self.target_critic_1 = QValueNet(state_dim, hidden_dim,action_dim).to(cfg.device)  
        # 第二个目标Q网络
        self.target_critic_2 = QValueNet(state_dim, hidden_dim,action_dim).to(cfg.device)  
        # 令目标Q网络的初始参数和Q网络一样
        self.target_critic_1.load_state_dict(self.critic_1.state_dict())
        self.target_critic_2.load_state_dict(self.critic_2.state_dict())
        # 优化器
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(),lr=cfg.actor_lr)
        self.critic_1_optimizer = torch.optim.Adam(self.critic_1.parameters(),lr=cfg.critic_lr)
        self.critic_2_optimizer = torch.optim.Adam(self.critic_2.parameters(),lr=cfg.critic_lr)
        # 使用alpha的log值,可以使训练结果比较稳定
        self.log_alpha = torch.tensor(np.log(0.01), dtype=torch.float)
        self.log_alpha.requires_grad = True  # 可以对alpha求梯度
        self.log_alpha_optimizer = torch.optim.Adam([self.log_alpha],lr=cfg.alpha_lr)
        # 目标熵的大小
        self.target_entropy = cfg.target_entropy  
        self.gamma = cfg.gamma
        self.tau = cfg.tau
        self.device = cfg.device

    def choose_action(self, state):
        state = torch.tensor([state], dtype=torch.float).to(self.device)
        probs = self.actor(state)
        action_dist = torch.distributions.Categorical(probs) #可以理解为将probs归一化，累加为1
        action = action_dist.sample()
        return action.item()
    
    def calc_target(self, rewards, next_states, dones):
        '''计算目标Q值,直接用策略网络的输出概率进行期望计算'''
        next_probs = self.actor(next_states)  # actor输出所有动作的概率
        next_log_probs = torch.log(next_probs + 1e-8)
        entropy = -torch.sum(next_probs * next_log_probs, dim=1, keepdim=True)
        
        # q value 
        q1_value = self.target_critic_1(next_states)
        q2_value = self.target_critic_2(next_states)
        min_qvalue = torch.sum(next_probs * torch.min(q1_value, q2_value),dim=1,keepdim=True)
        next_value = min_qvalue + self.log_alpha.exp() * entropy
        td_target = rewards + self.gamma * next_value * (1 - dones)
        return td_target

    def soft_update(self, net, target_net):
        for param_target, param in zip(target_net.parameters(),net.parameters()):
            param_target.data.copy_(param_target.data * (1.0 - self.tau) + param.data * self.tau)

    def update(self, transition_dict):
        states = torch.tensor(transition_dict['states'],dtype=torch.float).to(self.device)
        actions = torch.tensor(transition_dict['actions']).view(-1, 1).to(self.device)  # 动作不再是float类型
        rewards = torch.tensor(transition_dict['rewards'],dtype=torch.float).view(-1, 1).to(self.device)
        next_states = torch.tensor(transition_dict['next_states'],dtype=torch.float).to(self.device)
        dones = torch.tensor(transition_dict['dones'],dtype=torch.float).view(-1, 1).to(self.device)

        # 更新两个Q网络
        td_target = self.calc_target(rewards, next_states, dones)
        critic_1_q_values = self.critic_1(states).gather(1, actions)
        critic_1_loss = torch.mean(F.mse_loss(critic_1_q_values, td_target.detach()))    # 均方损失
        critic_2_q_values = self.critic_2(states).gather(1, actions)
        critic_2_loss = torch.mean(F.mse_loss(critic_2_q_values, td_target.detach()))    # 均方损失
        
        self.critic_1_optimizer.zero_grad()
        critic_1_loss.backward()
        self.critic_1_optimizer.step()
        self.critic_2_optimizer.zero_grad()
        critic_2_loss.backward()
        self.critic_2_optimizer.step()


        # 更新策略网络
        probs = self.actor(states)
        log_probs = torch.log(probs + 1e-8)
        # 直接根据概率计算熵
        entropy = -torch.sum(probs * log_probs, dim=1, keepdim=True)  
        self.entropy = entropy
        # 直接根据概率计算期望
        q1_value = self.critic_1(states)
        q2_value = self.critic_2(states)
        min_qvalue = torch.sum(probs * torch.min(q1_value, q2_value),dim=1,keepdim=True)  
        actor_loss = torch.mean(-self.log_alpha.exp() * entropy - min_qvalue)
        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # 更新 alpha 值
        alpha_loss = torch.mean((entropy - self.target_entropy).detach() * self.log_alpha.exp())
        self.log_alpha_optimizer.zero_grad()
        alpha_loss.backward()
        self.log_alpha_optimizer.step()

        # 更新两个目标网络
        self.soft_update(self.critic_1, self.target_critic_1)
        self.soft_update(self.critic_2, self.target_critic_2)
    
    def save(self,path):
        torch.save(self.actor.state_dict(), path+'actor.pt')
        torch.save(self.critic_1.state_dict(), path+'critic_1.pt')
        torch.save(self.critic_2.state_dict(), path+'critic_2.pt')
        torch.save(self.target_critic_1.state_dict(), path+'target_critic_1.pt')
        torch.save(self.target_critic_2.state_dict(), path+'target_critic_2.pt')

    def load(self,path):
        self.actor.load_state_dict(torch.load(path+'actor.pt')) 
        self.critic_1.load_state_dict(torch.load(path+'critic_1.pt')) 
        self.critic_2.load_state_dict(torch.load(path+'critic_2.pt')) 
        self.target_critic_1.load_state_dict(torch.load(path+'target_critic_1.pt')) 
        self.target_critic_2.load_state_dict(torch.load(path+'target_critic_2.pt')) 


class ReplayBuffer:
    def __init__(self, capacity):
        self.buffer = collections.deque(maxlen=capacity) 

    def push(self, state, action, reward, next_state, done): 
        self.buffer.append((state, action, reward, next_state, done)) 

    def sample(self, batch_size): 
        transitions = random.sample(self.buffer, batch_size)
        state, action, reward, next_state, done = zip(*transitions)
        return np.array(state), action, reward, np.array(next_state), done 

    def size(self): 
        return len(self.buffer)

# --------------  HER 经验回放池
class Trajectory:
    ''' 用来记录一条完整轨迹 '''
    def __init__(self, init_state):
        self.states = [init_state]
        self.actions = []
        self.rewards = []
        self.dones = []
        self.length = 0

    def store_step(self, action, state, reward, done):
        self.actions.append(action)
        self.states.append(state)
        self.rewards.append(reward)
        self.dones.append(done)
        self.length += 1

class ReplayBuffer_Trajectory:
    ''' 存储轨迹的经验回放池 '''
    def __init__(self, capacity):
        self.buffer = collections.deque(maxlen=capacity)

    def add_trajectory(self, trajectory):
        self.buffer.append(trajectory)

    def size(self):
        return len(self.buffer)

    def sample(self, batch_size, use_her, dis_threshold=0.15, her_ratio=0.8):
        batch = dict(states=[],
                     actions=[],
                     next_states=[],
                     rewards=[],
                     dones=[])
        for _ in range(batch_size):
            traj = random.sample(self.buffer, 1)[0]
            step_state = np.random.randint(traj.length)
            state = traj.states[step_state]
            next_state = traj.states[step_state + 1]
            action = traj.actions[step_state]
            reward = traj.rewards[step_state]
            done = traj.dones[step_state]

            if use_her and np.random.uniform() <= her_ratio:
                step_goal = np.random.randint(step_state + 1, traj.length + 1)
                goal = traj.states[step_goal][:2]  # 使用HER算法的future方案设置目标
                dis = np.sqrt(np.sum(np.square(next_state[:2] - goal)))
                reward = -1.0 if dis > dis_threshold else 0
                done = False if dis > dis_threshold else True
                state = np.hstack((state[:2], goal))
                next_state = np.hstack((next_state[:2], goal))

            batch['states'].append(state)
            batch['next_states'].append(next_state)
            batch['actions'].append(action)
            batch['rewards'].append(reward)
            batch['dones'].append(done)

        batch['states'] = np.array(batch['states'])
        batch['next_states'] = np.array(batch['next_states'])
        batch['actions'] = np.array(batch['actions'])
        return batch