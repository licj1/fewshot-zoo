import tensorflow as tf
import numpy as np
from model.network import *
from model.layers import *
from model.network import *
from model.loss import *


def get_protonet_ph(params):
    ph = {}

    # data shape [b, w, h, c]
    # label shape [b, ]
    # lr decay
    # is_training

    params_d = params['data']

    ph['support'] = tf.placeholder(dtype=tf.float32, 
                                   shape=[None, None] + params_d['x_size'],
                                   name='s')
    ph['query'] = tf.placeholder(dtype=tf.float32, 
                                 shape=[None, None] + params_d['x_size'],
                                 name='q')
    ph['label'] = tf.placeholder(dtype=tf.int64,
                                shape=[None, None],
                                name='label')
    ph['lr_decay'] = tf.placeholder(dtype=tf.float32, shape=[], name='lr_decay')
    ph['is_training'] = tf.placeholder(dtype=tf.bool, shape=[], name='is_training')

    return ph


def get_protonet_graph_var_and_targets(params, ph):
    graph = {}
    graph['ns'] = ns = tf.shape(ph['support'])[0]
    graph['nq'] = nq = tf.shape(ph['query'])[0]
    graph['n_way'] = n_way = tf.shape(ph['support'])[1]

    sx = tf.reshape(ph['support'], tf.convert_to_tensor([ns*n_way] + params['data']['x_size']))  # [ns * k, sz]
    qx = tf.reshape(ph['query'], tf.convert_to_tensor([nq*n_way] + params['data']['x_size']))    # [nq * k, sz]

    with tf.variable_scope('protonet', reuse=False)
        x = tf.concat([sx, qx], axis=0)
        z = four_block_cnn_encoder(x, params['network']['h_dim'], params['network']['z_dim'], 
                                   ph['is_training'], reuse=False)

    sz, qz = z[:ns*n_way, :], z[ns*n_way:, :]
    graph['support_z'], graph['query_z'] = sz, qz

    graph_vars = {'network': tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='protonet')}
    save_vars = graph_vars['network']

    loss, acc = proto_model(sz, qz, ns, nq, n_way, ph['label'])

    gen_op = tf.train.AdamOptimizer(params['network']['lr'] * ph['lr_decay'])
    gen_grads = gen_op.compute_gradients(loss=loss,
                                         var_list=graph_vars['network'])
    gen_train_op = gen_op.apply_gradients(grads_and_vars=gen_grads)

    targets = {
        'gen': {
            'train_op': gen_train_op,
            'entropy_loss': loss,
            'acc_loss': acc
        }
    }
    return graph, save_vars, targets


def get_protonet_model(params):
    ph = get_protonet_ph(params)
    graph, save_vars, targets = get_protonet_graph_var_and_targets(params, ph)
    return ph, graph, targets, save_vars