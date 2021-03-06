import tensorflow as tf


def normalize(x, dim=1):
    return x / tf.sqrt(tf.reduce_sum(x * x, axis=dim, keepdims=True))


def disc_gan_loss(real, fake):
    loss_real = tf.nn.sigmoid_cross_entropy_with_logits(
        labels=tf.ones_like(real),
        logits=real,
        name='loss_real')
    loss_fake = tf.nn.sigmoid_cross_entropy_with_logits(
        labels=tf.zeros_like(fake),
        logits=fake,
        name='loss_fake')
    d_loss = tf.reduce_mean(loss_real) + tf.reduce_mean(loss_fake)
    return d_loss


# TODO: incorporate reparameterization trick for z_real
def gen_gan_loss(real, fake):
    loss_fake = tf.nn.sigmoid_cross_entropy_with_logits(
        labels=tf.ones_like(fake),
        logits=fake,
        name='loss_fake_gen')
    g_loss = tf.reduce_mean(loss_fake)
    return g_loss

def disc_gan_loss(real, fake):
    loss_real = tf.nn.sigmoid_cross_entropy_with_logits(
        labels=tf.ones_like(real),
        logits=real,
        name='loss_real_disc')
    loss_fake = tf.nn.sigmoid_cross_entropy_with_logits(
        labels=tf.zeros_like(fake),
        logits=fake,
        name='loss_fake_disc')
    d_loss = tf.reduce_mean(loss_real) + tf.reduce_mean(loss_fake)
    return d_loss
 
def kl_divergence(pu, log_ps, qu):
    # pu [b, d]
    # ps [b, d]
    # qu [b, d]
    pair_kl = 0.5 * (-1 - log_ps + tf.square(pu - qu) + tf.exp(log_ps))
    return tf.reduce_sum(pair_kl, axis=1), tf.reduce_sum(tf.square(pu - qu), axis=1)


def wgan_gp_gp_loss(hat, hat_critic):
    '''
        real: critic for real data [b, ]
        fake: critic for fake data [b, ]
    '''
    gp_loss = tf.reduce_mean(
        (tf.sqrt(tf.reduce_sum(tf.gradients(hat_critic, hat)[0] ** 2,
                               reduction_indices=[1])) - 1.) ** 2
    )
    return gp_loss


def wgan_gp_wdist(real_critic, fake_critic):
    '''
        real: critic for real data [b, ]
        fake: critic for fake data [b, ]
    '''
    w_dist = tf.reduce_mean(real_critic) - tf.reduce_mean(fake_critic)
    return w_dist


def euclidean_distance(a, b, scale=1.0):
    # a.shape = N x D
    # b.shape = M x D
    N, D = tf.shape(a)[0], tf.shape(a)[1]
    M = tf.shape(b)[0]
    a = tf.tile(tf.expand_dims(a, axis=1), (1, M, 1))
    b = tf.tile(tf.expand_dims(b, axis=0), (N, 1, 1))
    return tf.reduce_sum(tf.square(a - b), axis=2) * scale

def cosine_similarity(x, y):
    x_norm = tf.nn.l2_normalize(x, axis=-1)
    y_norm = tf.nn.l2_normalize(y, axis=-1)
    y_norm_trans = tf.transpose(y_norm, [1, 0])
    sim = tf.matmul(x_norm, y_norm_trans)
    return sim

def inner_product(x, y):
    y_trans = tf.transpose(y, [1, 0])
    sim = tf.matmul(x, y_trans)
    return sim
