from __future__ import annotations


def apply_pretty_style():
    """Matplotlib 美化（深色背景 + 中文）。"""

    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    # 深色背景
    try:
        plt.style.use("dark_background")
    except Exception:
        pass

    # 字体：挑一个当前系统确实存在且支持中文的字体，避免中文 glyph warning
    candidates = [
        "Noto Sans CJK SC",
        "Noto Sans CJK TC",
        "Noto Sans CJK JP",
        "Noto Serif CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "Microsoft YaHei",
        "PingFang SC",
        "Hiragino Sans GB",
        "SimHei",
        "Arial Unicode MS",
        "Droid Sans Fallback",
        "DejaVu Sans",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = [name for name in candidates if name in available]
    if not chosen:
        chosen = ["DejaVu Sans"]
    primary = chosen[0]
    mpl.rcParams["font.family"] = [primary, "sans-serif"]
    mpl.rcParams["font.sans-serif"] = chosen + [name for name in candidates if name not in chosen]
    mpl.rcParams["axes.unicode_minus"] = False

    bg = "#0F172A"
    fg = "#E5EDF6"
    grid = "#334155"
    spine = "#94A3B8"

    mpl.rcParams.update(
        {
            "figure.figsize": (12.8, 6.8),
            "figure.facecolor": bg,
            "savefig.facecolor": bg,
            "axes.facecolor": bg,
            "axes.edgecolor": spine,
            "axes.labelcolor": fg,
            "axes.titlesize": 16,
            "axes.titleweight": "bold",
            "axes.titlepad": 12,
            "axes.labelsize": 12,
            "axes.grid": False,
            "text.color": fg,
            "xtick.color": fg,
            "ytick.color": fg,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "grid.color": grid,
            "grid.alpha": 0.22,
            "grid.linestyle": "--",
            "grid.linewidth": 0.8,
            "legend.fontsize": 10,
            "legend.facecolor": bg,
            "legend.edgecolor": grid,
            "legend.framealpha": 0.92,
            "lines.solid_capstyle": "round",
            "patch.linewidth": 0.8,
        }
    )
