import tensorflow as tf
import numpy as np
from model.network import *
from model.layers import *
from model.network import *
from model.loss import *


def dve_encoder_factory(inp, ph, params, reuse=True):
    if params['type'] == 'fc':
        return feedforward(inp, ph['is_training'], params, 'fc')
    else:
        raise NotImplementedError


def dve_decoder_factory(inp, ph, params):
    if params['type'] == 'fc':
        return feedforward(inp, ph['is_training'], params, 'fc')
    else:
        raise ValueError('Not Impelmented')


def dve_pretrain_encoder_factory(inp, ph):
    return four_block_cnn_encoder(inp, 64, 64, ph['is_training'])


def dve_pretrain_decoder_factory(inp, ph):
    nf = 64
    lx_z = tf.reshape(in_z, [-1, 5, 5, nf])    
    lx_z = tf.layers.conv2d_transpose(lx_z, nf, 3, strides=(2, 2),
                                      padding='same', use_bias=False)   #[10, 10]
    lx_z = tf.nn.relu(lx_z)
    lx_z = tf.layers.conv2d_transpose(lx_z, nf, 3, strides=(2, 2),
                                      padding='same', use_bias=False)   #[20, 20]
    lx_z = tf.nn.relu(lx_z)
    lx_z = tf.layers.conv2d_transpose(lx_z, nf, 3, strides=(2, 2),
                                      padding='same', use_bias=False)   #[40, 40]
    lx_z = tf.nn.relu(lx_z)
    lx_z = tf.layers.conv2d_transpose(lx_z, nf, 3, use_bias=False)      #[42, 42]
    lx_z = tf.nn.relu(lx_z)
    lx_z = tf.layers.conv2d_transpose(lx_z, 3, 3, strides=(2, 2),
                                      padding='same', use_bias=False)   #[84, 84]
    return lx_z

def get_dve_ph(params):
    ph = {}

    # data shape [b, w, h, c]
    # label shape [b, ]
    # lr decay
    # is_training

    # for training
    params_d = params['data']

    ph['data'] = tf.placeholder(dtype=tf.float32, 
                                shape=[None] + params_d['x_size'],
                                name='x')
    ph['label'] = tf.placeholder(dtype=tf.int64,
                                shape=[None],
                                name='label')
    ph['g_lr_decay'] = tf.placeholder(dtype=tf.float32, shape=[], name='g_lr_decay')
    ph['e_lr_decay'] = tf.placeholder(dtype=tf.float32, shape=[], name='e_lr_decay')
    ph['is_training'] = tf.placeholder(dtype=tf.bool, shape=[], name='is_training')
    ph['p_y_prior'] = tf.placeholder(dtype=tf.float32, shape=[params['data']['nclass'],], 
                                     name='p_y_prior')

    ph['ns'] = tf.placeholder(dtype=tf.int32, shape=[], name='ns')
    ph['nq'] = tf.placeholder(dtype=tf.int32, shape=[], name='nq')
    ph['n_way'] = tf.placeholder(dtype=tf.int32, shape=[], name='n_way')
    ph['eval_label'] = tf.placeholder(dtype=tf.int64,
                                shape=[None, None],
                                name='label')

    return ph

def get_dve_graph(params, ph):
    graph = {}
    rx = ph['data']            # [b, *x.shape]
    with tf.variable_scope('pretrain'):
        graph['x'] = x = dve_pretrain_encoder_factory(rx, ph)
        graph['pt_logits'] = tf.layers.dense(graph['x'], params['data']['nclass'], activation=None)

    # !TODO: remove batch_size dependency
    batch_size = params['train']['batch_size']
    z_dim = params['network']['z_dim']

    graph['one_hot_label'] = tf.one_hot(ph['label'], params['data']['nclass'])  # [b, K]
    with tf.variable_scope('dve', reuse=False):
        # Encoder
        with tf.variable_scope('encoder', reuse=False):
            mu_z, log_sigma_sq_z = dae_encoder_factory(x, ph, params['encoder'], False)
            graph['mu_z'], graph['log_sigma_sq_z'] = mu_z, log_sigma_sq_z
            noise = tf.random_normal(tf.shape(mu_z), 0.0, 1.0, 
                                     seed=params['train']['seed'])
            z = mu_z + tf.sqrt(tf.exp(log_sigma_sq_z)) * noise
            graph['z'] = z

        with tf.variable_scope('embedding', reuse=False):
            if params['embedding']['type'] == 'gaussian':
                nclass = params['network']['nclass']

                graph['mu'] = \
                    tf.get_variable('mu', [nclass, z_dim],
                                    initializer=tf.random_normal_initializer)

                graph['gt_mu'] = tf.gather(graph['mu'], ph['label'], axis=0)

        ns, nq, n_way = ph['ns'], ph['nq'], ph['n_way']
        
        sz = mu_z[:ns*n_way,:]
        qz = mu_z[ns*n_way:,:]
        graph['eval_ent'], graph['eval_acc'] = proto_model(sz, qz, ns, nq, n_way, ph['eval_label'])

        # Decoder
        with tf.variable_scope('decoder', reuse=False):
            if params['network']['use_decoder']:
                x_rec = dae_decoder_factory(z, ph, params['decoder'])
                graph['x_rec'] = x_rec

    return graph


def show_params(domain, var_list):
    print('Domain {}:'.format(domain))
    for var in var_list:
        print('{}: {}'.format(var.name, var.shape))

def get_dve_vars(params, ph, graph):
    pretrain_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='pretrain')
    saved_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='dve')
    encoder_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='dve/encoder')
    decoder_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='dve/decoder')
    network_vars = encoder_vars + decoder_vars
    embed_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='dve/embed')

    graph_vars = {
        'pretrain_vars': pretrain_vars,
        'disc': disc_vars,
        'encoder': encoder_vars,
        'decoder': decoder_vars,
        'embed': embed_vars,
        'gen': network_vars
    }
    show_params('pretrain', pretrain_vars)
    show_params('gen', network_vars)
    show_params('embed', embed_vars)
    return graph_vars, saved_vars, pretrain_vars


def get_dve_targets(params, ph, graph, graph_vars):
    # network and embedding part

    gen = {}
    gen['g_loss'] = 0.0

    # embedding loss
    gen['embed_loss'] = tf.reduce_mean(kl_divergence(graph['mu_z'], 
                                                     graph['log_sigma_sq_z'], graph['gt_mu']))

    gen['g_loss'] += gen['embed_loss'] * params['network']['e_m_weight']

    # reconstruction loss
    if params['network']['use_decoder']:
        gen['rec_loss'] = tf.reduce_mean(tf.square(graph['x'] - graph['x_rec']))
        gen['g_loss'] += gen['rec_loss'] * params['network']['rec_weight']

    # classfication loss
    log_p_y_prior = tf.log(tf.expand_dims(ph['p_y_prior'], 0))      # [1, K]
    dist = euclidean_distance(graph['z'], graph['mu'])         # [b, K]

    logits = -dist + log_p_y_prior

    log_yz = tf.nn.softmax_cross_entropy_with_logits(labels=graph['one_hot_label'], logits=logits, dim=1) # [b]
    acc = tf.reduce_mean(tf.cast(tf.equal(tf.argmax(logits, 1), ph['label']), tf.float32))   # [1,]

    gen['cls_loss'] = tf.reduce_mean(log_yz)
    gen['acc_loss'] = acc
    gen['g_loss'] += gen['cls_loss'] * params['network']['cls_weight']

    gen_op = tf.train.AdamOptimizer(params['network']['lr'] * ph['g_lr_decay'])
    gen_grads = gen_op.compute_gradients(loss=gen['g_loss'],
                                          var_list=graph_vars['gen'])
    gen_train_op = gen_op.apply_gradients(grads_and_vars=gen_grads)

    embed_op = tf.train.AdamOptimizer(params['embedding']['lr'] * ph['e_lr_decay'])
    embed_grads = embed_op.compute_gradients(loss=gen['g_loss'],
                                            var_list=graph_vars['embed'])
    embed_train_op = embed_op.apply_gradients(grads_and_vars=embed_grads)

    gen['train_gen'] = gen_train_op
    gen['train_embed'] = embed_train_op

    pretrain_loss = tf.nn.softmax_cross_entropy_with_logits(labels=graph['one_hot_label'], 
        logits=graph['pt_logits'], dim=1)
    pretrain_acc = tf.reduce_mean(tf.cast(tf.equal(tf.argmax(graph['pt_logits'], 1), ph['label']), tf.float32))
    pretrain_op = tf.train.AdamOptimizer(params['pretrain']['lr'] * ph['pretrain_lr_decay'])
    pretrain_grads = pretrain_op.compute_gradients(loss=pretrain_loss
                                          var_list=graph_vars['pretrain'])
    pretrain_train_op = pretrain_op.apply_gradients(grads_and_vars=pretrain_grads)
    pretrain_update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS, scope='pretrain')

    targets = {
        'pretrain': {
            'train': pretrain_train_op,
            'update': pretrain_update_ops,
        },
        'pretrain_eval': {
            'acc': pretrain_acc,
        },
        'gen': gen,
        'disc': disc,
        'eval': {
            'acc': graph['eval_acc'],
        }
    }

    return targets

def build_dve_model(params):
    ph = get_dve_ph(params)

    graph = get_dve_graph(params, ph)
    graph_vars, saved_vars, pretrain_vars = get_dve_vars(params, ph, graph)
    targets = get_dve_targets(params, ph, graph, graph_vars)

    return ph, graph, targets, saved_vars

