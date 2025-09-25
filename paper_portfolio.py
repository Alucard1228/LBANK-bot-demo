# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
import time

@dataclass
class Position:
    mode: str
    symbol: str
    side: str       # "long"
    entry: float
    qty: float
    sl: float
    tp: float
    open_time: int  # epoch seconds

class PaperPortfolio:
    def __init__(self, start_eq: float = 1000.0, fee_taker: float = 0.001):
        self.equity: float = float(start_eq)
        self.fee_taker: float = float(fee_taker)
        self.positions: Dict[Tuple[str, str], Position] = {}
        self.cum_fees: float = 0.0
        self.cum_pnl: float = 0.0

    def _key(self, mode: str, symbol: str) -> Tuple[str, str]:
        return (mode, symbol)

    def _notional(self, px: float, qty: float) -> float:
        return float(px) * float(qty)

    def can_open(self, mode: str, symbol: str) -> bool:
        return self._key(mode, symbol) not in self.positions

    def open(self, mode: str, symbol: str, side: str,
             entry: float, qty: float, sl: float, tp: float,
             reopen: bool = False) -> bool:
        key = self._key(mode, symbol)
        if key in self.positions and not reopen:
            return False

        if reopen:
            self.positions[key] = Position(
                mode=mode, symbol=symbol, side=side,
                entry=float(entry), qty=float(qty),
                sl=float(sl), tp=float(tp),
                open_time=int(time.time())
            )
            return True

        self.positions[key] = Position(
            mode=mode, symbol=symbol, side=side,
            entry=float(entry), qty=float(qty),
            sl=float(sl), tp=float(tp),
            open_time=int(time.time())
        )
        # si quieres fee en apertura, descomenta:
        # fee_open = self.fee_taker * self._notional(entry, qty)
        # self.equity -= fee_open
        # self.cum_fees += fee_open
        return True

    def mark(self, mode: str, symbol: str, last_px: float) -> Optional[str]:
        key = self._key(mode, symbol)
        pos = self.positions.get(key)
        if not pos:
            return None
        px = float(last_px)
        if pos.side == "long":
            if px >= pos.tp:
                return "TP"
            if px <= pos.sl:
                return "SL"
        else:
            if px <= pos.tp:
                return "TP"
            if px >= pos.sl:
                return "SL"
        return None

    def close(self, mode: str, symbol: str, exit_px: float):
        key = self._key(mode, symbol)
        pos = self.positions.get(key)
        if not pos:
            return 0.0, 0.0, None

        px = float(exit_px)
        if pos.side == "long":
            pnl = (px - pos.entry) * pos.qty
        else:
            pnl = (pos.entry - px) * pos.qty

        fee_close = self.fee_taker * self._notional(px, pos.qty)
        fee_total = fee_close  # si cobraste fee en apertura, súmala aquí
        pnl_net = pnl - fee_total

        self.equity += pnl_net
        self.cum_pnl += pnl
        self.cum_fees += fee_total

        del self.positions[key]
        return float(pnl_net), float(fee_total), pos
