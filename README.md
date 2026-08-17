# Calyre — implementação de referência (Fase 3)

Interpretador de referência da linguagem Calyre, descrito em
`calyre-fase1-fundamentos.md`, `calyre-fase2-sintaxe-e-tipos.md` e
`calyre-fase3-linguagem-real.md`.

## Estrutura

```
calyre_entry.py         ponto de entrada (usado por 'python' e pelo build do PyInstaller)
calyre/
  lexer.py               texto-fonte -> tokens (agora com mapas e interpolação de string)
  ast_nodes.py            nós da árvore sintática
  calyre_parser.py        tokens -> AST
  types.py                representação de tipos estáticos
  typechecker.py          checagem de tipos em tempo de compilação
  interpreter.py          executa a AST (ambiente, funções, structs, módulos, try/catch, assert)
  stdlib.py               biblioteca padrão: math, random, time, text, fs, python (interop)
  repl.py                 REPL interativo (mesmo lexer/parser/checker/interpretador)
  cli.py                  comando `calyre` (run/check/init/repl/add/remove/list/version)
examples/
  hello.cly                "Olá, mundo"
  demo.cly                  gramática do núcleo (Fase 2)
  modules_demo/             módulos locais, mapas, interpolação, try/catch, assert (Fase 3)
tests/                    76 testes (unittest) — lexer, parser, type checker, interpretador, módulos, stdlib
dist/
  calyre                    executável único, gerado via PyInstaller (Linux x86_64)
```

Nenhuma dependência externa é necessária para *rodar* a linguagem — apenas
Python 3.11+ padrão (`tomllib` é usado para ler `calyre.toml`). PyInstaller é
usado somente para *empacotar* em um único binário, para que o usuário final
não precise ter Python instalado.

## Rodando com Python (desenvolvimento)

```bash
python3 calyre_entry.py run examples/hello.cly
python3 calyre_entry.py run examples/demo.cly
python3 calyre_entry.py run examples/modules_demo/main.cly
python3 calyre_entry.py check examples/demo.cly   # type-checa sem rodar
python3 calyre_entry.py                            # abre o REPL
python3 calyre_entry.py init meu_projeto            # cria main.cly + calyre.toml
python3 calyre_entry.py version
```

## Rodando os testes

```bash
python3 -m unittest discover -s tests -v
```

## Rodando o binário empacotado (distribuição final)

```bash
./dist/calyre run examples/hello.cly
./dist/calyre                          # REPL
```

Este binário não exige Python, Node, CMake, LLVM nem qualquer outra ferramenta
instalada na máquina do usuário.

## Gerando o binário você mesmo (outras plataformas)

O binário incluído foi compilado em Linux x86_64. Para Windows ou macOS, rode
o mesmo comando *naquela* plataforma (PyInstaller não faz cross-compiling):

```bash
pip install pyinstaller
python -m PyInstaller --onefile --name calyre calyre_entry.py
```

## O que já funciona (Fase 3)

Tudo da Fase 2, mais:

- **Checagem estática de tipos**, antes de rodar (`calyre run`/`check`).
- **Módulos locais** (`use nome`, `use nome as apelido`) — qualquer arquivo
  `.cly` do projeto vira uma biblioteca importável.
- **Biblioteca padrão**: `math`, `random`, `time`, `text`, `fs`.
- **Ponte com Python**, restrita a uma lista segura de módulos
  (`use python` + `python.call(...)`).
- **Mapas** (`{ "a": 1 }`), **interpolação de string** (`"Hi, {name}"`),
  **`try/catch`**, **`error(...)`**, **`assert`** (com mensagem
  auto-explicativa quando falha).
- **REPL** (`calyre` sem argumentos), com multilinha automática e estado
  persistente.
- **`calyre.toml`** + `calyre init/add/remove/list` para dependências
  **locais** (sem registro remoto — ver Fase 3, seção 5, para o motivo).

Pendências explícitas (não implementadas, com justificativa em
`calyre-fase3-linguagem-real.md`): checagem de tipo *entre* módulos,
`trait`/interfaces, generics em declarações próprias, `calyre fmt`,
registro remoto de pacotes, módulos `json`/`system`/`path`/`http`.
