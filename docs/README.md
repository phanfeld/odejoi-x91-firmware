# Documentation sources

Sphinx project (Markdown through MyST, Read the Docs theme). Build from the repository root:

```bash
make -C docs html
```

The site is `docs/_build/html/index.html`. GitHub Actions (`.github/workflows/docs.yml`) builds it on every pull
request and publishes it to https://phanfeld.github.io/odejoi-x91-firmware/ on every push to `main`.

The Makefile uses Sphinx from `.venv-docs/`; set it up with:

```bash
python3 -m venv .venv-docs && .venv-docs/bin/pip install -r docs/requirements.txt
```

Without `python3-venv`'s pip: `python3 -m venv --without-pip .venv-docs && python3 -m pip --python .venv-docs/bin/python install -r docs/requirements.txt`.
