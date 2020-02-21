import os
import torch
import torchvision.transforms as transforms
from PIL import Image
from IPython.display import clear_output
from decimal import Decimal

Image.MAX_IMAGE_PIXELS = 1000000000 # Support gigapixel images


class StylenetArgs:
    def __init__(self):
        self.gpu = 'c'
        self.optimizer = 'lbfgs'
        self.learning_rate = 1e0
        self.lbfgs_num_correction = 100
        self.pooling = 'max'
        self.model_file = 'models/vgg19-d01eb7cb.pth'
        self.disable_check = False
        self.backend = 'nn'
        self.cudnn_autotune = False
        self.content_layers = 'relu4_2'
        self.style_layers = 'relu1_1,relu2_1,relu3_1,relu4_1,relu5_1'
        self.hist_layers = 'relu2_1,relu3_1,relu4_1,relu5_1'
        self.multidevice_strategy = '4,7,29'


def load_image(path, image_size, to_normalize=True):
    image = preprocess(path, image_size, to_normalize)
    return image


def random_image(h, w, c=3):
    image = torch.randn(c, h, w).mul(0.001).unsqueeze(0)
    return image


def random_image_like(base_image):
    _, C, H, W = base_image.size()
    return random_image(H, W, C)


def get_aspect_ratio(path):
    image = load_image(path, 1024)
    _, _, h, w = image.shape
    return w / h

    
# Preprocess an image before passing it to a model.
# We need to rescale from [0, 1] to [0, 255], convert from RGB to BGR,
# and subtract the mean pixel.
def preprocess(image_name, image_size, to_normalize=True):
    image = Image.open(image_name).convert('RGB')
    if type(image_size) is not tuple:
        image_size = tuple([int((float(image_size) / max(image.size))*x) for x in (image.height, image.width)])
    Loader = transforms.Compose([transforms.Resize(image_size), transforms.ToTensor()])
    rgb2bgr = transforms.Compose([transforms.Lambda(lambda x: x[torch.LongTensor([2,1,0])])])
    if to_normalize:
        Normalize = transforms.Compose([transforms.Normalize(mean=[103.939, 116.779, 123.68], std=[1,1,1])])
        tensor = Normalize(rgb2bgr(Loader(image) * 256)).unsqueeze(0)
    else:
        tensor = rgb2bgr(Loader(image)).unsqueeze(0)
    return tensor


#  Undo the above preprocessing.
def deprocess(output_tensor):
    Normalize = transforms.Compose([transforms.Normalize(mean=[-103.939, -116.779, -123.68], std=[1,1,1])])
    bgr2rgb = transforms.Compose([transforms.Lambda(lambda x: x[torch.LongTensor([2,1,0])])])
    output_tensor = bgr2rgb(Normalize(output_tensor.squeeze(0).cpu())) / 256
    output_tensor.clamp_(0, 1)
    Image2PIL = transforms.ToPILImage()
    image = Image2PIL(output_tensor.cpu())
    return image


# Combine the Y channel of the generated image and the UV/CbCr channels of the
# content image to perform color-independent style transfer.
def original_colors(content, generated):
    content, generated = deprocess(content.clone()), deprocess(generated.clone())    
    content_channels = list(content.convert('YCbCr').split())
    generated_channels = list(generated.convert('YCbCr').split())
    content_channels[0] = generated_channels[0]
    return Image.merge('YCbCr', content_channels).convert('RGB')


def get_style_image_paths(style_image_input):
    style_image_list = []
    for path in style_image_input:
        if os.path.isdir(path):
            images = (os.path.join(path, file) for file in os.listdir(path) 
                      if os.path.splitext(file)[1].lower() in [".jpg", ".jpeg", ".png", ".tiff"])
            style_image_list.extend(images)
        else:
            style_image_list.append(path)
    return style_image_list


def maybe_print(net, t, print_iter, num_iterations, loss):
    if print_iter != None and t % print_iter == 0:
        clear_output()
        print('Iteration %d/%d: '%(t, num_iterations))
        if net.content_weight > 0:
            print('  Content loss = %s' % ', '.join(['%.1e' % Decimal(module.loss.item()) for module in net.content_losses]))
        print('  Style loss = %s' % ', '.join(['%.1e' % Decimal(module.loss.item()) for module in net.style_losses if module.strength > 0]))
        print('  Histogram loss = %s' % ', '.join(['%.1e' % Decimal(module.loss.item()) for module in net.hist_losses if module.strength > 0]))
        if net.tv_weight > 0:
            print('  TV loss = %s' % ', '.join(['%.1e' % Decimal(module.loss.item()) for module in net.tv_losses]))
        print('  Total loss = %.2e' % Decimal(loss.item()))

def save(img, filename):
    disp = deprocess(img.clone())
    disp.save(str(filename))

def maybe_save_preview(img, t, save_iter, num_iterations, output_path):
    should_save = save_iter > 0 and t % save_iter == 0
    if not should_save:
        return
    output_filename, file_extension = os.path.splitext(output_path)
    output_filename = output_filename.replace('results', 'results/preview')
    filename = '%s_%04d%s' % (output_filename, t, file_extension)
    save(img, filename)
