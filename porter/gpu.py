# The device's GPU as the installer sees it: its family, and what it can do with a Switch game's textures.
# A Switch game's textures are BC-compressed. Adreno, Xclipse and NVIDIA sample them as they are. Mali (and Immortalis, its newer name), PowerVR and most other mobile GPUs
# have no BC at all, and the host decodes those textures on the CPU into RGBA8 / R8 / R8G8 (gfx_vk_tex.c bc_decode): 2 to 8 times their bytes in the device's memory, so the
# family decides how much memory a port wants and how long its loads take (docs/MALI.md). The GPU name is the GLES line SurfaceFlinger prints, "Qualcomm, Adreno (TM) 830, ...".
FAMILY = (('adreno', 'adreno'), ('xclipse', 'xclipse'), ('mali', 'mali'), ('immortalis', 'mali'), ('powervr', 'powervr'), ('nvidia', 'nvidia'))
BC = {'adreno': True, 'xclipse': True, 'nvidia': True, 'mali': False, 'powervr': False}
LOW_RAM = 6 << 30   # a device whose textures are decoded on the CPU wants more: the decoded ones alone can pass 3 GB


def family(gpu):
    """'adreno', 'xclipse', 'mali', 'powervr', 'nvidia' or 'unknown'"""
    g = (gpu or '').lower()
    for token, fam in FAMILY:
        if token in g: return fam
    return 'unknown'


def bc_textures(gpu):
    """Whether the GPU samples BC-compressed textures (the Switch's format, profile key requires bcn): None when the name says nothing about it"""
    return BC.get(family(gpu))


def needs_cpu_decode(gpu):
    """Whether the game's BC textures are decoded on the CPU here (a GPU without BC), so that a port of a game that requires them still runs"""
    return bc_textures(gpu) is False


def notes(gpu, requires=(), ram=None):
    """What this GPU means for the port about to be installed, as lines to say: [] when it has everything the profile requires"""
    if 'bcn' not in requires: return []
    bc = bc_textures(gpu)
    if bc is True: return []
    if bc is None:
        return [f'[RED] the game needs BC-compressed textures; whether this GPU ({gpu or "unknown"}) reads them is not known']
    out = [f'this GPU has no BC textures ({gpu}): the game\'s are decoded on the CPU, 2 to 8 times their bytes in memory. Loads take longer and 8 GB or more is wanted '
           '(DM_VK_BC_MAX_MB bounds the decoded textures, 2048 MB by default)']
    if ram is not None and ram < LOW_RAM:
        out.append(f'[RED] this device has {ram / 2**30:.1f} GB of memory: the decoded textures of a game this size can pass 3 GB, and Android ends an app that runs out')
    return out
