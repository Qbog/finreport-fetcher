from __future__ import annotations


def apply_pretty_style():
    """尽量让 matplotlib 图表更好看，并兼容中文。"""

    import matplotlib as mpl
    import matplotlib.pyplot as plt

    # 主题（不同 matplotlib 版本 style 名称略有差异）
    for style in ("seaborn-v0_8-whitegrid", "seaborn-whitegrid", "ggplot"):
        try:
            plt.style.use(style)
            break
        except Exception:
            continue

    # 字体：尽量找可用中文字体
    candidates = [
        "Microsoft YaHei",
        "PingFang SC",
        "Hiragino Sans GB",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "SimHei",
        # 有些 Linux 环境只装了 JP 版，但同样包含大部分汉字
        "Noto Sans CJK JP",
        "Noto Serif CJK JP",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    mpl.rcParams["font.sans-serif"] = candidates
    mpl.rcParams["axes.unicode_minus"] = False

    mpl.rcParams.update(
        {
            "figure.figsize": (12, 6),
            "axes.titlesize": 16,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
        }
    )
