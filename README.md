# Ages of the Island

An online strategy game: Settlers of Catan ideas played in real time, like Age of Empires. A server clock rolls the dice, settlers walk the island to found the first settlements, and everything is customizable. Built with Django.

- Game design: [docs/GAME_DESIGN.md](docs/GAME_DESIGN.md)
- Stage 1 technical plan: [docs/STAGE1_PLAN.md](docs/STAGE1_PLAN.md)

## Status

Stage 1 in progress. The rules engine (`engine/`) is pure Python and is being built first.

## Running the engine tests

```bash
python3 -m pip install "pydantic~=2.12"
python3 -m unittest discover -s engine -t . -p "test_*.py"
```
