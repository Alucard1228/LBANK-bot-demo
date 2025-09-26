# paper_portfolio.py
import time
from typing import List, Optional

class Position:
    def __init__(self, mode: str, symbol: str, side: str, entry: float, qty: float, sl: float, tp: float):
        self.mode = mode
        self.symbol = symbol
        self.side = side
        self.entry = entry
        self.qty = qty
        self.sl = sl
        self.tp = tp
        self.open_time = time.time()

class PaperPortfolio:
    def __init__(self, start_eq: float = 1000.0, fee_taker: float = 0.001):
        self.equity = start_eq
        self.start_eq = start_eq
        self.fee_taker = fee_taker
        self.positions: List[Position] = []  # Lista de posiciones

    def can_open(self, mode: str, symbol: str) -> bool:
        # Siempre permite abrir (el límite lo maneja main.py)
        return True

    def open(self, mode: str, symbol: str, side: str, entry: float, qty: float, sl: float, tp: float, reopen=False):
        if qty <= 0 or entry <= 0:
            return
        cost = entry * qty
        fee = cost * self.fee_taker
        if not reopen:
            if self.equity < cost + fee:
                return
            self.equity -= (cost + fee)
        pos = Position(mode, symbol, side, entry, qty, sl, tp)
        self.positions.append(pos)

    def close_position(self, position: Position, exit_price: float):
        """Cierra una posición individual y devuelve pnl y fee"""
        if position.side != "long":
            return 0.0, 0.0
        proceeds = exit_price * position.qty
        fee = proceeds * self.fee_taker
        pnl = proceeds - fee - (position.entry * position.qty)
        self.equity += (proceeds - fee)
        return pnl, fee

    def get_positions(self, mode: str, symbol: str) -> list:
        """Devuelve todas las posiciones abiertas para (modo, símbolo)"""
        return [p for p in self.positions if p.mode == mode and p.symbol == symbol]

    def remove_position(self, position: Position):
        """Elimina una posición de la lista"""
        if position in self.positions:
            self.positions.remove(position)
