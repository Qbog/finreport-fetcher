from __future__ import annotations

from dataclasses import dataclass

from .akshare_sina import AkshareSinaProvider
from .tushare_provider import TushareProvider


@dataclass
class ProviderConfig:
    provider: str  # auto|tushare|akshare
    prefer_order: list[str]
    tushare_token: str | None = None


def build_providers(cfg: ProviderConfig):
    providers = {
        "akshare": AkshareSinaProvider(),
        "tushare": TushareProvider(token=cfg.tushare_token),
    }

    def get_one(name: str):
        p = providers.get(name)
        if p is None:
            raise ValueError(f"未知 provider: {name}")
        if not p.supports():
            raise RuntimeError(f"provider 不可用或未安装依赖: {name}")
        return p

    if cfg.provider != "auto":
        return [get_one(cfg.provider)]

    res = []
    for name in cfg.prefer_order:
        try:
            p = providers.get(name)
            if p and p.supports():
                res.append(p)
        except Exception:
            continue
    if not res:
        raise RuntimeError("未找到可用的数据源 provider（请检查依赖安装情况）")
    return res
