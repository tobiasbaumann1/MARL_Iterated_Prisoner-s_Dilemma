import tensorflow as tf
import numpy as np
import logging
logging.basicConfig(filename='Planning_Agent.log',level=logging.DEBUG,filemode='w')
from Agents import Agent

RANDOM_SEED = 4
np.random.seed(RANDOM_SEED)
tf.set_random_seed(RANDOM_SEED)

class Planning_Agent(Agent):
    def __init__(self, env, underlying_agents, learning_rate=0.01, n_units = 4, gamma = 0.95, max_reward_strength = None, cost_param = 0):
        super().__init__(env, learning_rate, gamma)     
        self.planning_subagents = []
        for underlying_agent in underlying_agents:
            self.planning_subagents.append(
                Planning_Sub_Agent(env,underlying_agent,learning_rate,n_units,gamma, max_reward_strength, cost_param))

    def learn(self, s, a_players):
        for (a,planning_subagent) in zip(a_players,self.planning_subagents):
            planning_subagent.learn(s,a)

    def get_log(self):
        return [subagent.log for subagent in self.planning_subagents]

    def choose_action(self, s, player_actions):
        return [planning_subagent.choose_action(s,a) for (a,planning_subagent) in zip(player_actions,self.planning_subagents)]

class Planning_Sub_Agent(Agent):
    def __init__(self, env, underlying_agent, learning_rate=0.01, n_units = 4, gamma = 0.95, max_reward_strength = None, cost_param = 0):
        super().__init__(env, learning_rate, gamma)
        self.cost_param = cost_param
        self.underlying_agent = underlying_agent
        self.log = []
        self.max_reward_strength = max_reward_strength

        self.s = tf.placeholder(tf.float32, [1, env.n_features], "state")   
        self.a_player = tf.placeholder(tf.float32, None, "player_action")
        self.inputs = tf.concat([self.s,tf.reshape(self.a_player,(1,1))],1)

        with tf.variable_scope('Policy_p_'+str(underlying_agent.agent_idx)):
            # l1 = tf.layers.dense(
            #     inputs=self.inputs,
            #     units=n_units,    # number of hidden units
            #     activation=tf.nn.relu,
            #     kernel_initializer=tf.random_normal_initializer(0., .1),    # weights
            #     bias_initializer=tf.constant_initializer(0),  # biases
            #     name='l1_planning'
            # )

            self.l1 = tf.layers.dense(
                inputs=self.inputs,
                units=1,    # output units
                activation=None,
                kernel_initializer=tf.random_normal_initializer(0, .1),  # weights
                bias_initializer=tf.constant_initializer(0),  # biases
                name='actions_planning'
            )

            if max_reward_strength is None:
                self.action_layer = self.l1
            else:
                self.action_layer = tf.sigmoid(self.l1)

        with tf.variable_scope('Vp'):
            # Vp is trivial to calculate in this special case
            if max_reward_strength is not None:
                self.vp = 2 * max_reward_strength * (self.action_layer - 0.5)
            else:
                self.vp = self.action_layer

        with tf.variable_scope('V_total'):
            # V is trivial to calculate in this special case
            self.v = 4 * (self.a_player - 0.5) # omit contribution of second player because derivative vanishes

        with tf.variable_scope('cost_function'):
            log_prob_pi = tf.log(underlying_agent.get_action_prob_variable()[0,tf.cast(self.a_player,dtype = tf.int32)])
            theta = underlying_agent.get_policy_parameters()
            g_log_prob = [tf.gradients(log_prob_pi,param) for param in theta]
            g_log_prob = tf.concat([tf.reshape(param,[-1]) for param in g_log_prob],0)

            # policy gradient theorem
            self.g_Vp_d = g_log_prob * self.vp
            self.g_V_d = g_log_prob * self.v

            self.cost = - underlying_agent.learning_rate * tf.tensordot(self.g_Vp_d,self.g_V_d,1) + self.cost_param * tf.square(self.vp)

        with tf.variable_scope('trainPlanningAgent'):
            self.train_op = tf.train.AdamOptimizer(learning_rate).minimize(self.cost, 
                var_list = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='Policy_p_'+str(underlying_agent.agent_idx)))  

        self.sess.run(tf.global_variables_initializer())

    def learn(self, s, a_player):
        s = s[np.newaxis,:]
        feed_dict = {self.s: s, self.a_player: a_player, self.underlying_agent.get_state_variable(): s}
        self.sess.run([self.train_op], feed_dict)
        action,vp,v,cost,g_Vp_d,g_V_d = self.sess.run([self.action_layer,self.vp,self.v,self.cost,self.g_Vp_d,self.g_V_d], feed_dict)
        logging.info('Learning step')
        logging.info('Planning_action: ' + str(action))
        logging.info('Vp: ' + str(vp))
        logging.info('V: ' + str(v))
        logging.info('Gradient of V_p: ' + str(g_Vp_d))
        logging.info('Gradient of V: ' + str(g_V_d))
        logging.info('Cost: ' + str(cost))

    def choose_action(self, s, a):
        logging.info('Player action: ' + str(a))
        s = s[np.newaxis, :]
        action = self.sess.run(self.action_layer, {self.s: s, self.a_player: a})[0,0]
        if self.max_reward_strength is not None:
            action = 2 * self.max_reward_strength * (action - 0.5)
        logging.info('Planning action: ' + str(action))
        # Planning actions in the case of cooperation / defection
        if a == 0:
            a_p_defect = action
            a_p_coop = self.sess.run(self.action_layer, {self.s: s, self.a_player: 1})[0,0]
            if self.max_reward_strength is not None:
                a_p_coop = 2 * self.max_reward_strength * (a_p_coop-0.5)
        else:
            a_p_coop = action
            a_p_defect = self.sess.run(self.action_layer, {self.s: s, self.a_player: 0})[0,0]
            if self.max_reward_strength is not None:
                a_p_defect = 2 * self.max_reward_strength * (a_p_defect-0.5)
        self.log.append([a_p_defect,a_p_coop])
        return action

