import torch
import torch.nn as nn
import os.path as osp

import graphgallery as gg
from graphgallery import functional as gf


class TorchKeras(nn.Module):
    """Keras like PyTorch Model."""

    def __init__(self, *args, **kwargs):
        self.__doc__ = super().__doc__

        super().__init__(*args, **kwargs)

        # To be compatible with TensorFlow
        self._in_multi_worker_mode = dummy_function
        self._is_graph_network = dummy_function
        self.distribute_strategy = None

        # To be compatible with TensorBoard callbacks
        self._train_counter = 0
        self._test_counter = 0

        # initialize
        self.optimizer = None
        self.metrics = None
        self.loss = None

        # cache
        self.empty_cache()

    def from_cache(self, **kwargs):
        if not kwargs:
            return None

        def get(name, value):
            obj = self.cache.get(name, None)

            if obj is None:
                assert value is not None
                self.cache[name] = value
                obj = value
            return obj

        out = tuple(get(k, v) for k, v in kwargs.items())
        if len(out) == 1:
            out, = out
        return out

    def empty_cache(self):
        self.cache = gf.BunchDict()

    def train_step_on_batch(self,
                            x,
                            y,
                            out_index=None,
                            device="cpu"):
        self.train()
        optimizer = self.optimizer
        loss_fn = self.loss
        metrics = self.metrics
        optimizer.zero_grad()
        x, y = to_device(x, y, device=device)
        out = self(*x)
        if out_index is not None:
            out = out[out_index]
        loss = loss_fn(out, y)
        loss.backward()
        optimizer.step()
        if self.scheduler is not None:
            self.scheduler.step()
        for metric in metrics:
            metric.update_state(y.cpu(), out.detach().cpu())

        results = [loss.cpu().detach()] + [metric.result() for metric in metrics]
        return dict(zip(self.metrics_names, results))

    @torch.no_grad()
    def test_step_on_batch(self,
                           x,
                           y,
                           out_index=None,
                           device="cpu"):
        self.eval()
        loss_fn = self.loss
        metrics = self.metrics
        x, y = to_device(x, y, device=device)
        out = self(*x)
        if out_index is not None:
            out = out[out_index]
        loss = loss_fn(out, y)
        for metric in metrics:
            metric.update_state(y.cpu(), out.detach().cpu())

        results = [loss.cpu().detach()] + [metric.result() for metric in metrics]
        return dict(zip(self.metrics_names, results))

    @torch.no_grad()
    def predict_step_on_batch(self, x, out_index=None, device="cpu"):
        self.eval()
        x = to_device(x, device=device)
        out = self(*x)
        if out_index is not None:
            out = out[out_index]
        return out.cpu().detach()

    def build(self, inputs):
        # TODO
        pass

    def compile(self, loss=None, optimizer=None, metrics=None,
                scheduler=None):
        self.loss = loss
        self.optimizer = optimizer
        self.scheduler = scheduler
        if not isinstance(metrics, (list, tuple)):
            metrics = [metrics]
        self.metrics = metrics

    def reset_metrics(self):
        assert self.metrics is not None
        for metric in self.metrics:
            metric.reset_states()

    def reset_parameter(self):
        reset(self)

    @property
    def metrics_names(self):
        assert self.metrics is not None
        return ['loss'] + [metric.name for metric in self.metrics]

    def on_train_begin(self):
        pass

    def on_test_begin(self):
        pass

    def on_predict_begin(self):
        pass

    def summary(self):
        # TODO
        pass

    def save_weights(self,
                     filepath,
                     overwrite=True,
                     save_format=None,
                     **kwargs):
        ext = gg.file_ext()

        if not filepath.endswith(ext):
            filepath = filepath + ext

        if not overwrite and osp.isfile(filepath):
            proceed = gg.utils.ask_to_proceed_with_overwrite(filepath)
            if not proceed:
                return

        torch.save(self.state_dict(), filepath)

    def load_weights(self, filepath):
        ext = gg.file_ext()

        if not filepath.endswith(ext):
            filepath = filepath + ext

        checkpoint = torch.load(filepath)
        self.load_state_dict(checkpoint)

    def save(self, filepath, overwrite=True, save_format=None, **kwargs):
        ext = gg.file_ext()

        if not filepath.endswith(ext):
            filepath = filepath + ext

        if not overwrite and osp.isfile(filepath):
            proceed = gg.utils.ask_to_proceed_with_overwrite(filepath)
            if not proceed:
                return

        torch.save(self, filepath)

    @classmethod
    def load(cls, filepath):
        ext = gg.file_ext()

        if not filepath.endswith(ext):
            filepath = filepath + ext

        return torch.load(filepath)


def dummy_function(*args, **kwargs):
    ...


def reset(nn):
    def _reset(item):
        if hasattr(item, 'reset_parameters'):
            item.reset_parameters()

    if nn is not None:
        if hasattr(nn, 'children') and len(list(nn.children())) > 0:
            for item in nn.children():
                _reset(item)
        else:
            _reset(nn)


def to_device(x, y=None, device='cpu'):
    if not isinstance(x, (list, tuple)):
        x = [x]
    x = [_x.to(device) if hasattr(x, 'to') else _x for _x in x]

    if y is not None:
        if isinstance(y, (list, tuple)):
            y = [_y.to(device) if hasattr(y, 'to') else _y for _y in y]
        else:
            y = y.to(device)
        return x, y
    else:
        return x
