import argparse
import gin


def eval_mode(fn):
    def inner(self, *args, **kwargs):
        was_training = self.training
        self.eval()
        out = fn(self, *args, **kwargs)
        self.train(was_training)
        return out

    return inner


def parse_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("config_path", type=str, help="Path to gin config file.")
    args = parser.parse_args()
    gin.parse_config_file(args.config_path)
