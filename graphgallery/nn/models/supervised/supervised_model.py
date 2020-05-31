import os
import datetime
import numpy as np
import tensorflow as tf
import scipy.sparse as sp

from tqdm import tqdm
from tensorflow.keras import backend as K
from tensorflow.keras.utils import Sequence
from tensorflow.python.keras import callbacks as callbacks_module
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint

from graphgallery.utils.history import History
from graphgallery.nn.models import BaseModel


class SupervisedModel(BaseModel):
    """
        Base model for supervised learning.

        Arguments:
        ----------
            adj: `scipy.sparse.csr_matrix` (or `csc_matrix`) with shape (N, N)
                The input `symmetric` adjacency matrix, where `N` is the number of nodes 
                in graph.
            features: `np.array` with shape (N, F)
                The input node feature matrix, where `F` is the dimension of node features.
            labels: `np.array` with shape (N,)
                The ground-truth labels for all nodes in graph.
            device (String, optional): 
                The device where the model is running on. You can specified `CPU` or `GPU` 
                for the model. (default: :obj: `CPU:0`, i.e., the model is running on 
                the 0-th device `CPU`)
            seed (Positive integer, optional): 
                Used in combination with `tf.random.set_seed & np.random.seed & random.seed` 
                to create a reproducible sequence of tensors across multiple calls. 
                (default :obj: `None`, i.e., using random seed)
            name (String, optional): 
                Name for the model. (default: name of class)

    """

    def __init__(self, adj, x, labels=None, device='CPU:0', seed=None, name=None, **kwargs):
        super().__init__(adj, x, labels, device, seed, name, **kwargs)

    def build(self):
        """
            Build the model using customized hyperparameters.

        Note:
        ----------
            This method must be called before training/testing/predicting. 
            Use `model.build()`. The following `Arguments` are only commonly used 
            arguments, and other model-specific arguments are not introduced as follows.


        Arguments:
        ----------
            hiddens: `list` of integer 
                The number of hidden units of model. Note: the last hidden unit (`n_classes`)
                aren't nececcary to specified and it will be automatically added in the last 
                layer. 
            activations: `list` of string
                The activation function of model. Note: the last activation function (`softmax`) 
                aren't nececcary to specified and it will be automatically spefified in the 
                final output.              
            dropout: Float scalar
                Dropout rate for the hidden outputs.
            lr: Float scalar
                Learning rate for the model.
            l2_norm: Float scalar
                L2 normalize for the hidden layers. (usually only used in the first layer)
            use_bias: Boolean
                Whether to use bias in the hidden layers.

        """
        raise NotImplementedError

    def train(self, index_train, index_val=None,
              epochs=200, early_stopping=None,
              verbose=False, save_best=True, log_path=None, save_model=False,
              monitor='val_acc', early_stop_metric='val_loss'):
        """
            Train the model for the input `index_train` of nodes or `sequence`.

        Note:
        ----------
            You must compile your model before training/testing/predicting. Use `model.build()`.

        Arguments:
        ----------
            index_train: `np.array`, `list`, Integer scalar or `graphgallery.NodeSequence`
                the index of nodes (or sequence) that will be used during training.    
            index_val: `np.array`, `list`, Integer scalar or `graphgallery.NodeSequence`, optional
                the index of nodes (or sequence) that will be used for validation. 
                (default :obj: `None`, i.e., do not use validation during training)
            epochs: Postive integer
                The number of epochs of training.(default :obj: `200`)
            early_stopping: Postive integer or None
                The number of early stopping patience during training. (default :obj: `None`, 
                i.e., do not use early stopping during training)
            verbose: Boolean
                Whether to show the training details. (default :obj: `None`)
            save_best: Boolean
                Whether to save the best weights (accuracy of loss depend on `monitor`) 
                of training or validation (depend on `validation` is `False` or `True`). 
                (default :obj: `True`)
            log_path: String or None
                The path of saved weights/model. (default :obj: `None`, i.e., 
                `./log/{self.name}_weights`)
            save_model: Boolean
                Whether to save the whole model or weights only, if `True`, the `self.custom_objects`
                must be speficied if you are using customized `layer` or `loss` and so on.
            monitor: String
                One of (val_loss, val_acc, loss, acc), it determines which metric will be
                used for `save_best`. (default :obj: `val_acc`)
            early_stop_metric: String
                One of (val_loss, val_acc, loss, acc), it determines which metric will be 
                used for early stopping. (default :obj: `val_loss`)

        Return:
        ----------
            history: graphgallery.utils.History
                tensorflow like `history` instance.
        """
        # TODO use tensorflow callbacks

        # Check if model has been built
        if not self.built:
            raise RuntimeError('You must compile your model before training/testing/predicting. Use `model.build()`.')

        if isinstance(index_train, Sequence):
            train_data = index_train
        else:
            train_data = self.train_sequence(index_train)
            self.index_train = self.to_int(index_train)

        
        validation = index_val is not None

        if validation:
            if isinstance(index_val, Sequence):
                val_data = index_val
            else:
                val_data = self.test_sequence(index_val)
                self.index_val = self.to_int(index_val)

        history = History(monitor_metric=monitor,
                          early_stop_metric=early_stop_metric)

        if log_path is None:
            log_path = self.log_path
            
        if not log_path.endswith('.h5'):
            log_path += '.h5'                

        if not validation:
            history.register_monitor_metric('acc')
            history.register_early_stop_metric('loss')

        if verbose:
            pbar = tqdm(range(1, epochs+1))
        else:
            pbar = range(1, epochs+1)

        for epoch in pbar:

            if self.do_before_train is not None:
                self.do_before_train()

            loss, accuracy = self.do_forward(train_data)
            train_data.on_epoch_end()

            history.add_results(loss, 'loss')
            history.add_results(accuracy, 'acc')

            if validation:
                if self.do_before_validation is not None:
                    self.do_before_validation()

                val_loss, val_accuracy = self.do_forward(val_data, training=False)

                history.add_results(val_loss, 'val_loss')
                history.add_results(val_accuracy, 'val_acc')

            # record eoch and running times
            history.record_epoch(epoch)

            if save_best and history.save_best:
                self.save(log_path, save_model=save_model)

            # early stopping
            if early_stopping and history.time_to_early_stopping(early_stopping):
                msg = f'Early stopping with patience {early_stopping}.'
                if verbose:
                    pbar.set_description(msg)
                    pbar.close()
                break

            if verbose:
                msg = f'loss {loss:.2f}, acc {accuracy:.2%}'
                if validation:
                    msg += f', val_loss {val_loss:.2f}, val_acc {val_accuracy:.2%}'
                pbar.set_description(msg)

        if save_best:
            self.load(log_path, save_model=save_model)
            os.remove(log_path)            

        return history
    
    def train_v2(self, index_train, index_val=None,
              epochs=200, early_stopping=None,
              verbose=False, save_best=True, log_path=None, save_model=False,
              monitor='val_acc', early_stop_metric='val_loss', callbacks=None, **kwargs):
        """
            Train the model for the input `index_train` of nodes or `sequence`.

        Note:
        ----------
            You must compile your model before training/testing/predicting. Use `model.build()`.

        Arguments:
        ----------
            index_train: `np.array`, `list`, Integer scalar or `graphgallery.NodeSequence`
                the index of nodes (or sequence) that will be used during training.    
            index_val: `np.array`, `list`, Integer scalar or `graphgallery.NodeSequence`, optional
                the index of nodes (or sequence) that will be used for validation. 
                (default :obj: `None`, i.e., do not use validation during training)
            epochs: Postive integer
                The number of epochs of training.(default :obj: `200`)
            early_stopping: Postive integer or None
                The number of early stopping patience during training. (default :obj: `None`, 
                i.e., do not use early stopping during training)
            verbose: Boolean
                Whether to show the training details. (default :obj: `None`)
            save_best: Boolean
                Whether to save the best weights (accuracy of loss depend on `monitor`) 
                of training or validation (depend on `validation` is `False` or `True`). 
                (default :obj: `True`)
            log_path: String or None
                The path of saved weights/model. (default :obj: `None`, i.e., 
                `./log/{self.name}_weights`)
            save_model: Boolean
                Whether to save the whole model or weights only, if `True`, the `self.custom_objects`
                must be speficied if you are using customized `layer` or `loss` and so on.
            monitor: String
                One of (val_loss, val_acc, loss, acc), it determines which metric will be
                used for `save_best`. (default :obj: `val_acc`)
            early_stop_metric: String
                One of (val_loss, val_acc, loss, acc), it determines which metric will be 
                used for early stopping. (default :obj: `val_loss`)
            callbacks: tensorflow.keras.callbacks. (default :obj: `None`)
            kwargs: other keyword arguments.

        Return:
        ----------
            A `tf.keras.callbacks.History` object. Its `History.history` attribute is
            a record of training loss values and metrics values
            at successive epochs, as well as validation loss values
            and validation metrics values (if applicable).

        """
        
        if not tf.__version__>='2.2.0':
            raise RuntimeError(f'This method is only work for tensorflow version >= 2.2.0.')

        # Check if model has been built
        if not self.built:
            raise RuntimeError('You must compile your model before training/testing/predicting. Use `model.build()`.')

        if isinstance(index_train, Sequence):
            train_data = index_train
        else:
            train_data = self.train_sequence(index_train)
            self.index_train = self.to_int(index_train)

        validation = index_val is not None

        if validation:
            if isinstance(index_val, Sequence):
                val_data = index_val
            else:
                val_data = self.test_sequence(index_val)
                self.index_val = self.to_int(index_val)

        model = self.model
        print(model)
        
        if not isinstance(callbacks, callbacks_module.CallbackList):
            callbacks = callbacks_module.CallbackList(callbacks,
                                                      add_history=True,
                                                      add_progbar=True,
                                                      verbose=verbose,
                                                      epochs=epochs)
        if early_stopping is not None:
            es_callback = EarlyStopping(monitor=early_stop_metric, 
                                        patience=early_stopping, 
                                        mode='auto', 
                                        verbose=kwargs.pop('es_verbose', 0))
            callbacks.append(es_callback)
            
        if save_best:
            if log_path is None:
                log_path = self.log_path

            if not log_path.endswith('.h5'):
                log_path += '.h5'           
                
            mc_callback = ModelCheckpoint(log_path,
                                          monitor=monitor,
                                          save_best_only=True,
                                          save_weights_only=not save_model,
                                          verbose=verbose)
            callbacks.append(mc_callback)
        callbacks.set_model(model)
        
        # leave it blank for the future
        allowed_kwargs = set([])
        unknown_kwargs = set(kwargs.keys()) - allowed_kwargs
        if unknown_kwargs:
            raise TypeError(
                "Invalid keyword argument(s) in `__init__`: %s" % (unknown_kwargs,))        
            
        callbacks.on_train_begin()            
        
        for epoch in range(epochs):
            callbacks.on_epoch_begin(epoch)

            if self.do_before_train is not None:
                self.do_before_train()
                
            callbacks.on_train_batch_begin(0)
            loss, accuracy = self.do_forward(train_data)
            train_data.on_epoch_end()
            
            training_logs = {'loss': loss, 'acc': accuracy}
            callbacks.on_train_batch_end(0, training_logs)
            
            if validation:
                if self.do_before_validation is not None:
                    self.do_before_validation()

                val_loss, val_accuracy = self.do_forward(val_data, training=False)
                training_logs.update({'val_loss': val_loss, 'val_acc': val_accuracy})
                
            callbacks.on_epoch_end(epoch, training_logs)
            
            if model.stop_training:
                break
                
                
        callbacks.on_train_end()            

        if save_best:
            self.load(log_path, save_model=save_model)
            os.remove(log_path)            
            

        return model.history    

    def test(self, index, **kwargs):
        """
            Test the output accuracy for the `index` of nodes or `sequence`.

        Note:
        ----------
            You must compile your model before training/testing/predicting.
            Use `model.build()`.

        Arguments:
        ----------
            index: `np.array`, `list`, Integer scalar or `graphgallery.NodeSequence`
            The index of nodes (or sequence) that will be tested.    

            **kwargs (optional): Additional arguments of
                :method:`do_before_test`.   

        Return:
        ----------
            loss: Float scalar
                Output loss of forward propagation. 
            accuracy: Float scalar
                Output accuracy of prediction.        
        """

        # TODO record test logs like self.train() or self.train_v2()
        if not self.built:
            raise RuntimeError('You must compile your model before training/testing/predicting. Use `model.build()`.')

        if isinstance(index, Sequence):
            test_data = index
        else:
            test_data = self.test_sequence(index)
            self.index_test = self.to_int(index)

        if self.do_before_test is not None:
            self.do_before_test(**kwargs)

        loss, accuracy = self.do_forward(test_data, training=False)

        return loss, accuracy

    def do_forward(self, sequence, training=True):
        """
            Forward propagation for the input `sequence`. This method will be called 
            in `train` and `test`, you can rewrite it for you customized training/testing 
            process. If you want to specify your customized data during traing/testing/predicting, 
            you can implement a sub-class of `graphgallery.NodeSequence`, wich is iterable 
            and yields `inputs` and `labels` in each iteration. 


        Note:
        ----------
            You must compile your model before training/testing/predicting. 
            Use `model.build()`.

        Arguments:
        ----------
            sequence: `graphgallery.NodeSequence`
                The input `sequence`.    
            trainng (Boolean, optional): 
                Indicating training or test procedure. (default: :obj:`True`)

        Return:
        ----------
            loss: Float scalar
                Output loss of forward propagation.
            accuracy: Float scalar
                Output accuracy of prediction.

        """
        model = self.model
        
        if training:
            forward_fn = model.train_on_batch
        else:
            forward_fn = model.test_on_batch

        model.reset_metrics()

        with tf.device(self.device):
            for inputs, labels in sequence:
                loss, accuracy = forward_fn(x=inputs, y=labels, reset_metrics=False)

        return loss, accuracy

    def predict(self, index, **kwargs):
        """
            Predict the output probability for the `index` of nodes.

        Note:
        ----------
            You must compile your model before training/testing/predicting. 
            Use `model.build()`.

        Arguments:
        ----------
            index: `np.array`, `list` or integer scalar
                The index of nodes that will be computed.    

            **kwargs (optional): Additional arguments of
                :method:`do_before_predict`.   

        Return:
        ----------
            The predicted probability of each class for each node, 
            shape (len(index), n_classes).

        """

        if not self.built:
            raise RuntimeError('You must compile your model before training/testing/predicting. Use `model.build()`.')

        if self.do_before_predict is not None:
            self.do_before_predict(**kwargs)

    def train_sequence(self, index):
        """
            Construct the training sequence for the `index` of nodes.


        Arguments:
        ----------
            index: `np.array`, `list` or integer scalar
                The index of nodes used in training.

        Return:
        ----------
            The sequence of `graphgallery.NodeSequence` for the nodes.

        """

        raise NotImplementedError

    def test_sequence(self, index):
        """
            Construct the testing sequence for the `index` of nodes.

        Note:
        ----------
            If not implemented, this method will call `train_sequence` automatically.

        Arguments:
        ----------
            index: `np.array`, `list` or integer scalar
                The index of nodes used in testing.

        Return:
        ----------
            The sequence of `graphgallery.NodeSequence` for the nodes.
        """
        return self.train_sequence(index)

    def test_predict(self, index):
        """
            Predict the output accuracy for the `index` of nodes.

        Note:
        ----------
            You must compile your model before training/testing/predicting. 
            Use `model.build()`.

        Arguments:
        ----------
            index: `np.array`, `list` or integer scalar
                The index of nodes that will be computed.    

        Return:
        ----------
            accuracy: Float scalar
                The output accuracy of the `index` of nodes.

        """
        index = self.to_int(index)
        logit = self.predict(index)
        predict_class = logit.argmax(1)
        labels = self.labels[index]
        return (predict_class == labels).mean()

    @tf.function
    def __call__(self, inputs):
        return self.model(inputs)

    @property
    def weights(self):
        """Return the weights of model, type `tf.Tensor`."""
        return self.model.weights

    @property
    def np_weights(self):
        """Return the weights of model, type `np.array`."""
        return [weight.numpy() for weight in self.weights]

    @property
    def trainable_variables(self):
        """Return the trainable weights of model, type `tf.Tensor`."""
        return self.model.trainable_variables

    @property
    def close(self):
        """Close the session of model and set `built` to False."""
        self.set_model(None)
        self.built = None
        K.clear_session()