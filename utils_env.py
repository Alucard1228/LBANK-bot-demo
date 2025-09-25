# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

def load_env(dotenv_path: str = ".env"):
    try:
        load_dotenv(dotenv_path=dotenv_path, override=True, verbose=True)
    except Exception as e:
        print(f"[WARN] .env parse error: {e}")
    return os.environ.copy()

def parse_int(x, d=0):
    try: return int(float(str(x).strip()))
    except: return d

def parse_float(x, d=0.0):
    try: return float(str(x).strip())
    except: return d

def parse_bool(x, d=False):
    s = str(x).strip().lower()
    return True if s in ("1","true","yes","y","on") else False if s in ("0","false","no","n","off") else d

def parse_csv(x):
    return [t.strip() for t in str(x or "").split(",") if t.strip()]

def get_mode_profile(mode: str) -> str:
    s = (mode or "").lower()
    if "agres" in s: return "agresivo"
    if "conserv" in s: return "conservador"
    return "moderado"
