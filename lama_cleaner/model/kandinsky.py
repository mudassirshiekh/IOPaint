import PIL.Image
import cv2
import numpy as np
import torch

from lama_cleaner.model.base import DiffusionInpaintModel
from lama_cleaner.model.utils import get_scheduler
from lama_cleaner.schema import Config


class Kandinsky(DiffusionInpaintModel):
    pad_mod = 64
    min_size = 512

    def init_model(self, device: torch.device, **kwargs):
        from diffusers import AutoPipelineForInpainting

        fp16 = not kwargs.get("no_half", False)
        use_gpu = device == torch.device("cuda") and torch.cuda.is_available()
        torch_dtype = torch.float16 if use_gpu and fp16 else torch.float32

        model_kwargs = {
            "local_files_only": kwargs.get("local_files_only", kwargs["sd_run_local"]),
            "torch_dtype": torch_dtype,
        }

        # self.pipe_prior = KandinskyPriorPipeline.from_pretrained(
        #     self.prior_name, **model_kwargs
        # ).to("cpu")
        #
        # self.model = KandinskyInpaintPipeline.from_pretrained(
        #     self.model_name, **model_kwargs
        # ).to(device)
        self.model = AutoPipelineForInpainting.from_pretrained(
            self.model_name, **model_kwargs
        ).to(device)

        self.callback = kwargs.pop("callback", None)

    def forward(self, image, mask, config: Config):
        """Input image and output image have same size
        image: [H, W, C] RGB
        mask: [H, W, 1] 255 means area to repaint
        return: BGR IMAGE
        """
        scheduler_config = self.model.scheduler.config
        scheduler = get_scheduler(config.sd_sampler, scheduler_config)
        self.model.scheduler = scheduler

        generator = torch.manual_seed(config.sd_seed)
        if config.sd_mask_blur != 0:
            k = 2 * config.sd_mask_blur + 1
            mask = cv2.GaussianBlur(mask, (k, k), 0)[:, :, np.newaxis]
        mask = mask.astype(np.float32) / 255
        img_h, img_w = image.shape[:2]

        output = self.model(
            prompt=config.prompt,
            negative_prompt=config.negative_prompt,
            image=PIL.Image.fromarray(image),
            mask_image=mask[:, :, 0],
            height=img_h,
            width=img_w,
            num_inference_steps=config.sd_steps,
            guidance_scale=config.sd_guidance_scale,
            output_type="np",
            callback=self.callback,
        ).images[0]

        output = (output * 255).round().astype("uint8")
        output = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
        return output

    def forward_post_process(self, result, image, mask, config):
        if config.sd_match_histograms:
            result = self._match_histograms(result, image[:, :, ::-1], mask)

        if config.sd_mask_blur != 0:
            k = 2 * config.sd_mask_blur + 1
            mask = cv2.GaussianBlur(mask, (k, k), 0)
        return result, image, mask

    @staticmethod
    def is_downloaded() -> bool:
        # model will be downloaded when app start, and can't switch in frontend settings
        return True


class Kandinsky22(Kandinsky):
    name = "kandinsky2.2"
    model_name = "kandinsky-community/kandinsky-2-2-decoder-inpaint"