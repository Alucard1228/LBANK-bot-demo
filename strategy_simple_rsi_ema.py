# strategy_simple_rsi_ema.py
# Archivo mantenido por compatibilidad, pero sin lógica real

class StrategyParams:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def make_signal(df_ltf, df_htf, params):
    # Esta función ya no se usa en el nuevo main.py
    return {"side": None}