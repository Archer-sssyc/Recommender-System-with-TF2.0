"""
Created on Dec 20, 2020
Updated on Nov 07, 2021
Reference: "Neural Collaborative Filtering", WWW, 2017
@author: Ziyao Geng(zggzy1996@163.com)
"""
import tensorflow as tf
from tensorflow.keras import Model
from tensorflow.keras.layers import Embedding, Dense, Input
from tensorflow.keras.regularizers import l2

from reclearn.layers import MLP
from reclearn.models.losses import bpr_loss, hinge_loss


class NCF(Model):
    def __init__(self, fea_cols, hidden_units=None, activation='relu', dnn_dropout=0.,
                 is_batch_norm=False, loss_name='bpr_loss', gamma=0.5, embed_reg=1e-6, seed=None):
        """
        NCF model
        :param fea_cols: A dict containing {'user_num':, 'item_num:, 'embed_dim':, ...}
        :param hidden_units: A list. The list of hidden layer units's numbers, such as [64, 32, 16, 8].
        :param activation: A string. The name of activation function, like 'relu', 'sigmoid' and so on.
        :param dnn_dropout: A scalar. The rate of dropout .
        :param is_batch_norm: A boolean. Whether using batch normalization or not.
        :param loss_name: A string. You can specify the current pair-loss function as "bpr_loss" or "hinge_loss".
        :param gamma: A scalar. If hinge_loss is selected as the loss function, you can specify the margin.
        :param embed_reg: A scalar. The regularizer of embedding.
        :param seed: A int scalar.
        """
        super(NCF, self).__init__()
        if hidden_units is None:
            hidden_units = [64, 32, 16, 8]
        # MF user embedding
        self.mf_user_embedding = Embedding(input_dim=fea_cols['user_num'],
                                           input_length=1,
                                           output_dim=fea_cols['embed_dim'],
                                           embeddings_initializer='random_normal',
                                           embeddings_regularizer=l2(embed_reg))
        # MF item embedding
        self.mf_item_embedding = Embedding(input_dim=fea_cols['item_num'],
                                           input_length=1,
                                           output_dim=fea_cols['embed_dim'],
                                           embeddings_initializer='random_normal',
                                           embeddings_regularizer=l2(embed_reg))
        # MLP user embedding
        self.mlp_user_embedding = Embedding(input_dim=fea_cols['user_num'],
                                            input_length=1,
                                            output_dim=fea_cols['embed_dim'],
                                            embeddings_initializer='random_normal',
                                            embeddings_regularizer=l2(embed_reg))
        # MLP item embedding
        self.mlp_item_embedding = Embedding(input_dim=fea_cols['user_num'],
                                            input_length=1,
                                            output_dim=fea_cols['embed_dim'],
                                            embeddings_initializer='random_normal',
                                            embeddings_regularizer=l2(embed_reg))
        # dnn
        self.mlp = MLP(hidden_units, activation=activation, dnn_dropout=dnn_dropout, is_batch_norm=is_batch_norm)
        self.dense = Dense(1, activation=None)
        # loss name
        self.loss_name = loss_name
        self.gamma = gamma
        # seed
        tf.random.set_seed(seed)

    def call(self, inputs):
        # user info
        mf_user_embed = self.mf_user_embedding(inputs['user'])  # (None, embed_dim)
        mlp_user_embed = self.mlp_user_embedding(inputs['user'])  # (None, embed_dim)
        # item
        mf_pos_embed = self.mf_item_embedding(inputs['pos_item'])  # (None, embed_dim)
        mf_neg_embed = self.mf_item_embedding(inputs['neg_item'])  # (None, neg_num, embed_dim)
        mlp_pos_embed = self.mlp_item_embedding(inputs['pos_item'])  # (None, embed_dim)
        mlp_neg_embed = self.mlp_item_embedding(inputs['neg_item'])  # (None, neg_num, embed_dim)
        # MF
        mf_pos_vector = tf.nn.sigmoid(tf.multiply(mf_user_embed, mf_pos_embed))  # (None, embed_dim)
        mf_neg_vector = tf.nn.sigmoid(tf.multiply(tf.expand_dims(mf_user_embed, axis=1), mf_neg_embed))  # (None, neg_num, dim)
        # MLP
        mlp_pos_vector = tf.concat([mlp_user_embed, mlp_pos_embed], axis=-1)  # (None, 2 * embed_dim)
        mlp_neg_vector = tf.concat([tf.tile(tf.expand_dims(mlp_user_embed, axis=1), [1, mlp_neg_embed.shape[1], 1]),
                                    mlp_neg_embed], axis=-1)  # (None, neg_num, 2 * embed_dim)
        mlp_pos_vector = self.mlp(mlp_pos_vector)  # (None, dim)
        mlp_neg_vector = self.mlp(mlp_neg_vector)  # (None, neg_num, dim)
        # concat
        pos_vector = tf.concat([mf_pos_vector, mlp_pos_vector], axis=-1)  # (None, embed_dim+dim)
        neg_vector = tf.concat([mf_neg_vector, mlp_neg_vector], axis=-1)  # (None, neg_num, embed_dim+dim)
        # result
        pos_scores = tf.tile(self.dense(pos_vector), [1, neg_vector.shape[1]])  # (None, neg_num)
        neg_scores = tf.squeeze(self.dense(neg_vector), axis=-1)  # (None, neg_num)
        # loss
        if self.loss_name == 'bpr_loss':
            losses = bpr_loss(pos_scores, neg_scores)
        else:
            losses = hinge_loss(pos_scores, neg_scores, gamma)
        self.add_loss(losses)
        logits = tf.concat([pos_scores, neg_scores], axis=-1)
        return logits

    def summary(self):
        inputs = {
            'user': Input(shape=(), dtype=tf.int32),
            'pos_item': Input(shape=(), dtype=tf.int32),
            'neg_item': Input(shape=(1,), dtype=tf.int32)  # suppose neg_num=1
        }
        Model(inputs=inputs, outputs=self.call(inputs)).summary()