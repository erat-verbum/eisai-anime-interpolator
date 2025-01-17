import glob

from _util.util_v0 import * ; import _util.util_v0 as uutil
from _util.twodee_v0 import * ; import _util.twodee_v0 as u2d
from _util.pytorch_v0 import * ; import _util.pytorch_v0 as utorch
import _util.distance_transform_v0 as udist

import _train.frame_interpolation.models.ssldtm as models

device = torch.device('cuda')


# raft helper
from _train.frame_interpolation.helpers.raft_v1 import rfr_new as uraft
class RAFT(nn.Module):
    def __init__(self, path='./checkpoints/anime_interp_full.ckpt'):
        super().__init__()
        self.raft = uraft.RFR(Namespace(
            small=False,
            mixed_precision=False,
        ))
        if path is not None:
            sd = torch.load(path)['model_state_dict']
            self.raft.load_state_dict({
                k[len('module.flownet.'):]: v
                for k,v in sd.items()
                if k.startswith('module.flownet.')
            }, strict=False)
        return
    def forward(self, img0, img1, flow0=None, iters=12, return_more=False):
        if flow0 is not None:
            flow0 = flow0.flip(dims=(1,))
        out = self.raft(img1, img0, iters=iters, flow_init=flow0)
        return out[0].flip(dims=(1,)), (locals() if return_more else None)

# wrapper
def interpolate(ssl, dtm, x, t=0.5, return_more=False):
    with torch.no_grad():
        out_ssl,_ = ssl(x, t=t, return_more=True)
        out_dtm,_ = dtm(x, out_ssl, _, return_more=return_more)
        ans = I(out_dtm[0,:3])
    return ans, (locals() if return_more else None)

def get_frame_num(path: os.PathLike) -> int:
    name = os.path.basename(path).replace(".png", "")
    return int(name)


def infer(frames_dir):
    # ap = argparse.ArgumentParser()
    # ap.add_argument('img0', type=str)
    # ap.add_argument('img1', type=str)
    # ap.add_argument('--fps', type=int, default=12)
    # ap.add_argument('--out', type=str, default='./temp/interpolation')
    # args = ap.parse_args()

    # uutil.mkdir(args.out)

    # load models
    ssl = models.SoftsplatLite()
    dtm = models.DTM()
    ssl.load_state_dict(torch.load('./checkpoints/ssl.pt'))
    dtm.load_state_dict(torch.load('./checkpoints/dtm.pt'))
    ssl = ssl.to(device).eval()
    dtm = dtm.to(device).eval()
    raft = RAFT().eval().to(device)

    file_paths = sorted(glob.glob(frames_dir + '/**/*.png', recursive=True))

    prev_frame_num = 1
    prev_file_path = file_paths[0]
    for file_path in tqdm(file_paths):
        frame_num = get_frame_num(file_path)

        num_intermediary_frames = frame_num - prev_frame_num -1

        if num_intermediary_frames > 0:
            # load images
            img0 = I(prev_file_path).convert('RGB')
            img1 = I(file_path).convert('RGB')
            assert img0.size==img1.size
            original_size = img0.size
            img0 = img0.resize((540,960))
            img1 = img1.resize((540,960))

            # interpolate
            n = num_intermediary_frames + 2
            ts = np.linspace(0,1,n)[1:-1]
            # img0.resize(original_size).save(f'{args.out}/{n-1:02d}_{0:02d}.png')
            # img1.resize(original_size).save(f'{args.out}/{n-1:02d}_{n-1:02d}.png')
            with torch.no_grad():
                img0,img1 = img0.t()[None,:3].to(device), img1.t()[None,:3].to(device)
                flow0,_ = raft(img0, img1)
                flow1,_ = raft(img1, img0)
                x = {
                    'images': torch.stack([img0,img1], dim=1),
                    'flows': torch.stack([flow0,flow1], dim=1),
                }
            for i,t in enumerate(ts):
                intermediary_frame_num = prev_frame_num + i + 1
                intermediary_frame_file_path = os.path.join(frames_dir, f"{intermediary_frame_num:0>10d}.png")

                ans,_ = interpolate(ssl, dtm, x, t=t)

                ans.resize(original_size).save(intermediary_frame_file_path)

        prev_frame_num = frame_num
        prev_file_path = file_path


# evaluate
if __name__=='__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('dir', type=str)
    args = ap.parse_args()
    infer(args.dir)



