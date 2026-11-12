"""Point d'entree : python run.py [--config chemin/config.json]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main():
    ap = argparse.ArgumentParser(description="GTC Comptabilite Clients")
    ap.add_argument("--config", help="chemin du fichier config.json")
    args = ap.parse_args()
    from gtc_compta.ui.app import main as run
    run(args.config)


if __name__ == "__main__":
    main()
