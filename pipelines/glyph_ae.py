import torch as T
import torch.nn as nn
import torch.nn.functional as F
import matplotlib.pyplot as plt
import numpy as np

import utils.nn as tu
import utils.vis as vis
import utils.mp as mp

from tqdm.auto import trange

import kornia
import random


class MsgEncoder(tu.Module):
    def __init__(self, msg_size, img_channels):
        super().__init__()

        self.net = nn.Sequential(
            tu.reshape(-1, msg_size, 1, 1),
            tu.deconv_block(msg_size, 128, ks=5, s=2, p=1),
            # nn.Dropout(0.2),
            tu.deconv_block(128, 64, ks=5, s=1, p=2),
            # nn.Dropout(0.3),
            tu.deconv_block(64, 32, ks=5, s=1, p=2),
            tu.deconv_block(32, 16, ks=5, s=2, p=1),
            # nn.Dropout(0.3),
            tu.deconv_block(16, 8, ks=5, s=1, p=2),
            tu.deconv_block(8, 8, ks=5, s=2, p=2),
            # nn.Dropout(0.01),
            tu.deconv_block(8, 4, ks=5, s=2, p=2),
            tu.deconv_block(4, img_channels, ks=4, s=2, p=0, a=nn.Sigmoid()),
        )

    def forward(self, z):
        return self.net(z)


class MsgDecoder(tu.Module):
    def __init__(self, in_channels, msg_size):
        super().__init__()

        self.net = tu.conv_to_flat(
            [in_channels, 128, 128, 64, 32, 32],
            msg_size,
            ks=3,
            s=2,
        )

    def forward(self, x):
        return self.net(x)


class ReverseAE(tu.Module):
    def __init__(self, msg_size, img_channels):
        super().__init__()
        self.msg_size = msg_size
        self.encoder = MsgEncoder(msg_size, img_channels)
        self.decoder = MsgDecoder(img_channels, msg_size)

        # This is done so that te decoder parameters are initialized
        imgs = self.encoder(self.sample(bs=1))
        self.decoder(imgs)

    def get_data_gen(self, bs):
        while True:
            X = self.sample(bs)
            yield X, X

    def sample(self, bs):
        return T.randn(bs, self.msg_size).to(self.device)

    def forward(self, bs):
        msg = self.sample(bs)
        img = self.encoder(msg)
        return img

    def configure_optim(self, lr, noise_size):
        self.noise_size = noise_size
        self.optim = T.optim.Adam(self.parameters(), lr)

    def optim_forward(self, X):
        def apply_noise(t):
            bs = t.shape[0]

            noise = T.randn_like(t).to(self.device) * 1
            offsets = T.randn(bs, 2).to(self.device) * t.shape[-1] * 0.1
            angles = T.randn(bs).to(self.device) * 30
            scales = T.randn(bs).to(self.device) / 5 + 1

            t = kornia.rotate(t, angles)
            t = kornia.scale(t, scales)
            t = kornia.translate(t, offsets)
            t = t + noise

            return t

        img = self.encoder(X)
        img = apply_noise(img)
        pred_msg = self.decoder(img)

        return pred_msg


if __name__ == "__main__":
    from datetime import datetime

    msg_size = 512
    model = ReverseAE(msg_size, img_channels=3)
    model = model.to('cuda')
    model.make_persisted('.models/glyph-ae.h5')

    epochs = 5
    model.configure_optim(lr=0.001, noise_size=1)

    msgs = model.sample(100)
    run_id = f'img_{datetime.now()}'

    with vis.fig([12, 12]) as ctx, mp.fit(
        model=model,
        its=512 * epochs,
        data_gen=model.get_data_gen(bs=128),
    ) as fit:
        # fit.join()
        for i in fit.wait:
            # epoch = fit.it // epochs
            # model.configure_optim(lr=0.001, noise_size=0.5)

            model.persist()
            # ctx.clear()
            imgs = model.encoder(msgs)
            imgs.reshape(10, 10, *imgs.shape[-3:]).imshow()

            plt.savefig(f'.imgs/screen_{run_id}.png')

    model.persist()
