# Começando com Calyre

Calyre é uma linguagem de programação feita para ser fácil de ler e de aprender, e útil em programas reais.
O código é igual em qualquer idioma: as palavras-chave, a biblioteca padrão e as mensagens são em inglês.
Este texto é só uma introdução em português. A referência completa (em inglês) está em [../SPEC.md](../SPEC.md).

## Rodando

```text
calyre                      abre o REPL: digite código e veja o resultado
calyre run programa.cly     roda um arquivo
calyre init meu_projeto     cria main.cly e calyre.toml
```

## O primeiro programa

```calyre run
let nome = "Ana"
let idade = 30
print("Olá, {nome}! Ano que vem você terá {idade + 1} anos.")
```

```output
Olá, Ana! Ano que vem você terá 31 anos.
```

`let` cria uma variável. O texto entre `{ }` é calculado e colocado no texto. Os tipos são descobertos sozinhos,
e erros de tipo aparecem **antes** de o programa rodar:

```calyre error
let idade = 30
idade = "trinta"
```

```output
main.cly:2:9: error: cannot assign str to 'idade', which is int
```

## Decisões, repetições e funções

```calyre run
func classificar(nota: float) -> str
    if nota >= 7.0
        return "aprovado"
    elif nota >= 5.0
        return "recuperação"
    else
        return "reprovado"
    end
end

for nota in [8.5, 6.0, 3.0]
    print("{nota}: {classificar(nota)}")
end
```

```output
8.5: aprovado
6.0: recuperação
3.0: reprovado
```

Blocos terminam com `end`. Condições precisam ser verdadeiras ou falsas (`bool`): escreva uma comparação,
como `len(itens) > 0`, em vez de usar a própria lista como condição.

## Listas, mapas e texto

```calyre run
let compras: list<str> = []
compras.append("pão")
compras.append("leite")
print(compras, len(compras), compras.contains("leite"))

let precos = {"pão": 1.5, "leite": 4.0}
print(precos.get("café") ?? 0.0)
print("  calyre  ".trim().upper())
```

```output
["pão", "leite"] 2 true
0.0
CALYRE
```

## Valores que podem faltar

`str?` significa "um texto ou `none`". O compilador obriga você a tratar o caso `none` antes de usar o valor:

```calyre run
func saudacao(apelido: str?) -> str
    if apelido == none
        return "Olá, visitante!"
    end
    return "Olá, {apelido}!"
end

print(saudacao(none))
print(saudacao("Ana"))
```

```output
Olá, visitante!
Olá, Ana!
```

## Erros, testes e formatação

* `try ... catch e ... end` captura erros: `e.message` diz o que aconteceu.
* `calyre test` roda funções chamadas `test_...` em arquivos `test_*.cly`, usando `assert`.
* `calyre fmt` arruma o estilo do código; `calyre lint` aponta código suspeito.

Próximos passos: [a referência da linguagem](../SPEC.md), [a biblioteca padrão](../STDLIB.md) e [as ferramentas](../TOOLS.md).
