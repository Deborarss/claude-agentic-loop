# Guia de estudo: claude-agentic-loop

Este guia leva você do zero até entender (e conseguir modificar) cada linha deste projeto.
Siga as partes **na ordem**: cada uma usa o que a anterior ensinou.

| Parte | O que você faz | Tempo |
|---|---|---|
| [1. Preparar o ambiente](#parte-1-preparar-o-ambiente) | Instalar, rodar os testes, rodar o agente | 15 min |
| [2. Conceitos antes do código](#parte-2-conceitos-antes-do-código) | Entender o que é um agente e como ele conversa com o Claude | 30 min |
| [3. Leitura guiada do código](#parte-3-leitura-guiada-do-código) | Ler os 6 arquivos na ordem certa | 1h30 |
| [4. Rodar tudo, passo a passo](#parte-4-rodar-tudo-passo-a-passo) | Testes, agente real, forçar cada guarda | 30 min |
| [5. Exercícios práticos](#parte-5-exercícios-práticos) | Modificar o projeto sozinha | 1h+ |
| [6. Conexão com a prova CCA-F](#parte-6-conexão-com-a-prova-cca-f) | Checklist do que cai na prova | 15 min |
| [7. Glossário](#parte-7-glossário) · [8. Problemas comuns](#parte-8-problemas-comuns) | Consulta | — |

> 💡 **Dica de estudo:** deixe o código aberto num lado da tela e este guia no outro.
> Sempre que o guia citar um arquivo, abra e procure o trecho.

---

## Parte 1: Preparar o ambiente

### O que você precisa ter instalado

| Ferramenta | Para quê | Como conferir |
|---|---|---|
| Python 3.11+ | Linguagem do projeto | `python --version` |
| [uv](https://docs.astral.sh/uv/) | Gerencia o Python, as dependências e o ambiente virtual | `uv --version` |
| Git | Controle de versão | `git --version` |
| Claude Code (logado) | O Agent SDK usa o login dele | `claude auth status` → `"loggedIn": true` |

### Passo 1: Abrir o terminal na pasta do projeto

No PowerShell:

```powershell
cd "$HOME\Documents\lab claude\claude-agentic-loop"
```

> `$HOME` é a sua pasta de usuário (ex.: `C:\Users\<seu-usuario>`). Ajuste o resto se o projeto estiver em outro lugar.
> As aspas são obrigatórias porque o caminho tem espaço (`lab claude`).

Se estiver em outro computador, clone primeiro:

```powershell
git clone https://github.com/Deborarss/claude-agentic-loop.git
cd claude-agentic-loop
```

### Passo 2: Instalar as dependências

```powershell
uv sync
```

**O que isso faz:** lê o [`pyproject.toml`](../pyproject.toml), cria uma pasta `.venv` (ambiente virtual isolado,
só deste projeto) e instala o que está listado lá (`claude-agent-sdk`, `tzdata`, `pytest`...).
O arquivo `uv.lock` garante que todo mundo instale **exatamente as mesmas versões**.

### Passo 3: Rodar os testes

```powershell
uv run pytest
```

Você deve ver algo como `48 passed`. Esses testes **não chamam o Claude** e não gastam nada (a Parte 3 explica como).

> `uv run <comando>` = "rode este comando usando o ambiente virtual do projeto". Você não precisa ativar o `.venv` na mão.

### Passo 4: Conferir o login do Claude Code

```powershell
claude auth status
```

Procure `"loggedIn": true` e `"authMethod": "claude.ai"`. Se aparecer `false`, rode `claude auth login`.

### Passo 5: Rodar o agente pela primeira vez

```powershell
uv run agent "Quanto é 17*23 e que horas são em São Paulo?"
```

Resposta esperada (a hora vai mudar):

```
Aqui estão as respostas:
**Cálculo:** 17 × 23 = **391**
**Hora em São Paulo:** 18:17:25 ...

[parada: completed | voltas: 3 | tokens: 433]
```

A última linha é o **resumo da parada**: *por que* o agente parou, quantas voltas deu e quantos tokens usou.
Todo o projeto gira em torno de garantir que essa linha **sempre** exista e sempre tenha um motivo claro.

✅ **Checkpoint:** se os testes passaram e o agente respondeu, o ambiente está pronto.

---

## Parte 2: Conceitos antes do código

### 2.1 O Claude sozinho não "faz" nada

Quando você chama a API do Claude, ele **só devolve texto**. Ele não executa código, não consulta banco de dados,
não sabe que horas são. Então como um agente "usa ferramentas"?

**Resposta:** o *seu* programa faz o trabalho. O Claude só **pede**:

> Claude: "Eu gostaria de chamar a tool `calculator` com `{"expression": "17*23"}`."
> Seu programa: *executa a função Python* → "391"
> Seu programa: "Claude, o resultado foi 391."
> Claude: "17 × 23 = 391."

### 2.2 O que é uma *tool*

Uma tool é uma função que você **descreve** para o Claude com três coisas:

```python
{
    "name": "calculator",                                  # nome
    "description": "Avalia uma expressão aritmética...",   # quando usar (o Claude lê isso!)
    "input_schema": {                                      # quais argumentos (JSON Schema)
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
}
```

> 🎯 A `description` é um **prompt**: é ela que faz o Claude escolher a tool certa. Descrição ruim = tool mal usada.

### 2.3 A conversa, mensagem por mensagem

A Messages API recebe uma **lista de mensagens** alternando `user` e `assistant`.
Veja a conversa real do exemplo `17*23`:

**① Você envia:**
```json
[{"role": "user", "content": "Quanto é 17*23?"}]
```

**② O Claude responde** com `stop_reason: "tool_use"`, que quer dizer "parei porque quero usar uma tool":
```json
{"role": "assistant", "content": [
    {"type": "text", "text": "Vou calcular."},
    {"type": "tool_use", "id": "toolu_01", "name": "calculator", "input": {"expression": "17*23"}}
]}
```

**③ Seu programa executa a tool e devolve o resultado** numa mensagem `user`:
```json
{"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "toolu_01", "content": "391", "is_error": false}
]}
```

> ⚠️ **Regra de ouro:** todo `tool_use` precisa de um `tool_result` com o **mesmo `id`** na mensagem seguinte.

**④ Você envia a lista inteira de novo** (①+②+③). O Claude responde com `stop_reason: "end_turn"`:
```json
{"role": "assistant", "content": [{"type": "text", "text": "17 × 23 = 391."}]}
```

`end_turn` = "terminei". Fim.

### 2.4 Então... o que é um *agente*?

É só **repetir os passos ②-③ num `while`** até o Claude parar de pedir tools:

```
enquanto verdadeiro:
    resposta = chamar_claude(mensagens)
    se resposta.stop_reason != "tool_use":
        parar            ← o MODELO decidiu terminar
    executar as tools pedidas
    adicionar resultados às mensagens
```

Isso é o **agentic loop**. Repare no detalhe perigoso: **quem decide parar é o modelo.**

### 2.5 Por que isso é perigoso: *safe termination*

E se o modelo **nunca** decidir parar?

| Situação | O que acontece sem proteção |
|---|---|
| O modelo chama a mesma tool, com os mesmos argumentos, sem parar | Loop infinito |
| Cada volta envia a conversa inteira de novo | O custo em tokens cresce a cada volta |
| Uma tool sempre falha e o modelo insiste | Loop infinito de erros |
| A API trava ou demora | O programa fica pendurado para sempre |
| A resposta é cortada no meio (`max_tokens`) | Você acha que acabou, mas a resposta está incompleta |

**Safe termination** = colocar **guardas** que garantem que o loop *sempre* termina, *sempre* com um motivo explícito.
É exatamente isso que este projeto implementa.

### 2.6 Os valores de `stop_reason` que você precisa conhecer

| `stop_reason` | Significado | O que o loop faz |
|---|---|---|
| `tool_use` | "Quero usar uma tool" | **Continua**: executa e devolve o resultado |
| `end_turn` | "Terminei" | Para ✅ |
| `max_tokens` | "Minha resposta foi cortada pelo limite de saída" | Para ⚠️ (resposta incompleta!) |
| `stop_sequence` | Encontrou uma sequência de parada que você definiu | Para ✅ |
| `pause_turn` | Pausa de uma tool que roda no servidor da Anthropic | Continua |
| `refusal` | O modelo se recusou | Para ⚠️ |

### 2.7 Duas formas de fazer a mesma coisa

| | Loop **na mão** (`raw_loop.py`) | **Agent SDK** (`sdk_agent.py`) |
|---|---|---|
| Quem escreve o `while` | Você | O SDK |
| Onde ficam as guardas | No seu código | Na **configuração** (`max_turns`, hooks...) |
| Autenticação | API key (paga por uso) | Login do Claude Code (sua assinatura) |
| Para que serve aqui | **Entender** como funciona por baixo | **Rodar** de verdade |

> A prova cobra os dois: entender o loop por dentro **e** saber configurar um framework.

✅ **Checkpoint:** tente explicar em voz alta o que é `tool_use`, `tool_result` e `end_turn` e por que um agente precisa de guardas.

---

## Parte 3: Leitura guiada do código

Leia **nesta ordem**. Cada arquivo depende só dos anteriores.

```
tools.py ──► termination.py ──► raw_loop.py ──► tests/ ──► sdk_agent.py ──► main.py
 (o que o      (quando         (o loop         (como       (o mesmo loop     (a linha
 agente faz)    parar)          na mão)         testar)     com o SDK)        de comando)
```

---

### 3.1 [`src/agent_loop/tools.py`](../src/agent_loop/tools.py): o que o agente sabe fazer

**Ideia principal:** cada tool é definida **uma vez só** (`ToolSpec`) e reaproveitada pelas duas implementações.

**Leia e procure:**

1. **`calculator`**: repare que **não usa `eval()`**. Por quê? `eval("__import__('os').system('del *')")` executaria
   qualquer comando! Em vez disso, o código usa `ast.parse` para transformar o texto numa árvore e só aceita
   números e operadores (`_BIN_OPS`, `_UNARY_OPS`). Qualquer outra coisa → `ToolError`.
   > 🎯 **Lição de segurança:** o input de uma tool vem do modelo, e o modelo pode ter sido manipulado por um texto malicioso. **Nunca confie no input de uma tool.**

2. **`ToolError`**: um erro *esperado* ("divisão por zero", "chamado não encontrado").

3. **`execute_tool`**: a função mais importante do arquivo. Ela **nunca levanta exceção**: sempre devolve `(texto, is_error)`.
   ```python
   except ToolError as exc:
       return str(exc), True      # ← o erro vira TEXTO para o Claude ler
   ```
   > 🎯 **Por quê?** Se a tool falhar e o programa quebrar, o agente morre. Se o erro voltar como `is_error: true`,
   > o Claude lê "Chamado INC9999 não encontrado" e **se adapta** (você viu isso acontecer no teste real!).

4. **`anthropic_tool_definitions()`**: converte para o formato da Messages API (o JSON da seção 2.2).

5. **`build_sdk_server()`**: converte para o formato do Agent SDK, um **MCP server in-process**.
   Os nomes viram `mcp__lab__calculator` (`mcp__<servidor>__<tool>`). O parâmetro `on_result` avisa as
   guardas sempre que uma tool termina (vamos usar isso na 3.5).

**❓ Perguntas para checar o entendimento:**
- Por que `2**1000` é rejeitado? (dica: procure `abs(right) > 100`)
- O que o Claude recebe se pedir uma tool que não existe?
- Onde estão os dados dos chamados? Por que são fictícios?

---

### 3.2 [`src/agent_loop/termination.py`](../src/agent_loop/termination.py): quando parar

**Ideia principal:** todas as regras de parada ficam num lugar só, separadas do loop.

**Leia e procure:**

1. **`StopReason`**: um `Enum` com **todos** os motivos possíveis de parada. Por que um Enum e não strings soltas?
   Porque assim é impossível errar a digitação (`"max_iteration"` vs `"max_iterations"`) e fica fácil ver a lista completa.

2. **`Limits`**: os números de cada guarda, com valores padrão:
   ```python
   max_iterations = 10       # voltas no loop
   max_total_tokens = 50_000 # orçamento
   timeout_seconds = 120.0   # tempo de relógio
   max_repeated_calls = 3    # mesma chamada 3x → para
   max_consecutive_errors = 3
   ```

3. **`AgentResult`**: o que o agente devolve. Repare: **sempre** tem um `stop_reason`. Não existe resultado sem motivo.

4. **`map_model_stop_reason`**: traduz o `stop_reason` da API (tabela da seção 2.6). Devolve `None` = "continue".
   Repare no `case _: return StopReason.ERROR`: se a API inventar um valor novo, o loop **para** em vez de continuar
   às cegas. Isso é programação defensiva.

5. **`TerminationGuard`**: a classe com estado. Cada método devolve um `StopReason` (pare!) ou `None` (pode seguir):

   | Método | Quando é chamado | Verifica |
   |---|---|---|
   | `before_iteration()` | Início de cada volta | Máximo de voltas e timeout |
   | `record_usage()` | Depois de cada resposta | Orçamento de tokens |
   | `check_tool_call()` | Antes de executar uma tool | Chamada repetida |
   | `record_tool_result()` | Depois de executar uma tool | Erros seguidos |

6. **`call_signature`**: como detectar "a mesma chamada"? Juntando o nome com os argumentos em JSON **ordenado**
   (`sort_keys=True`). Sem ordenar, `{"a":1,"b":2}` e `{"b":2,"a":1}` pareceriam diferentes.

7. **O `clock` injetável**: `TerminationGuard(limits, clock=time.monotonic)`. Por que não chamar `time.monotonic()` direto?
   Porque nos testes passamos um relógio **falso** e "pulamos" 999 segundos instantaneamente. (Veja `test_timeout`.)

**❓ Perguntas:**
- Um sucesso no meio de erros zera o contador de erros? (dica: `record_tool_result`)
- Por que `time.monotonic()` e não `time.time()`? (dica: o que acontece se o relógio do Windows for ajustado?)

---

### 3.3 [`src/agent_loop/raw_loop.py`](../src/agent_loop/raw_loop.py): o loop na mão ⭐

**Este é o arquivo mais importante para a prova.** Leia devagar, linha por linha, com a seção 2.3 aberta ao lado.

**Roteiro de leitura da função `run_raw_loop`:**

| Linha(s) | O que acontece | Conceito |
|---|---|---|
| `messages = [{"role": "user", ...}]` | Começa a conversa | Passo ① |
| `def finish(reason)` | Função auxiliar: todo `return` passa por ela | Sempre há um motivo |
| `while True:` | O loop | Agentic loop |
| `guard.before_iteration()` | Guarda: voltas e timeout | Safe termination |
| `client.messages.create(...)` | Chama o Claude com `model`, `system`, `tools`, `messages` | Messages API |
| `except Exception` | Rede caiu? Para com `ERROR`, **não tenta de novo para sempre** | Falha segura |
| `messages.append({"role": "assistant", ...})` | Guarda a resposta no histórico | Passo ② |
| `guard.record_usage(...)` | Soma os tokens | Orçamento |
| `map_model_stop_reason(...)` | `end_turn` → para; `tool_use` → segue | seção 2.6 |
| `for block in blocks:` | Para cada `tool_use`... | |
| `guard.check_tool_call(...)` | ...confere repetição... | Detecção de loop |
| `execute_tool(...)` | ...executa... | |
| `tool_results.append({... "tool_use_id": block["id"] ...})` | ...e monta o resultado **com o mesmo id** | Regra de ouro |
| `messages.append({"role": "user", "content": tool_results})` | Devolve tudo numa mensagem `user` | Passo ③ |

**O `client` é injetado** (vem como parâmetro). O loop não sabe se está falando com o Claude de verdade ou com um
cliente falso. Isso é **injeção de dependência**, e é o que torna o loop testável sem gastar nada.

**❓ Perguntas:**
- Se o Claude pedir 2 tools na mesma resposta, quantas mensagens `user` são adicionadas? (Resposta: 1, com 2 `tool_result`.)
- Em que ordem as guardas são checadas numa volta?
- O que acontece com `final_text` se a última resposta não tiver texto?

---

### 3.4 [`tests/`](../tests/): como testar um agente sem gastar nada

**Ideia principal:** um agente depende de um modelo (lento, pago, imprevisível). Para testar, **trocamos o modelo por um roteiro**.

1. **[`fake_client.py`](../tests/fake_client.py)**: imita o `anthropic.Anthropic()`. Você entrega uma lista de respostas prontas e
   ele devolve uma por chamada. Com `repeat_last=True`, repete a última para sempre (perfeito para simular um modelo "travado").
   Ele também **grava** cada chamada em `client.calls`, para o teste conferir o que foi enviado.

2. **[`test_raw_loop.py`](../tests/test_raw_loop.py)**: leia `test_caminho_feliz_com_duas_tools` primeiro. Ele roteiriza a conversa
   da seção 2.3 e confere que os `tool_result` voltaram com os ids certos. Depois leia um teste por guarda:

   | Teste | Como força a situação |
   |---|---|
   | `test_max_iterations_para_modelo_que_nunca_termina` | 100 respostas pedindo tools diferentes |
   | `test_chamada_repetida_detecta_loop` | Sempre a mesma chamada (`repeat_last=True`) |
   | `test_muitos_erros_de_tool_seguidos` | Chamados que não existem |
   | `test_orcamento_de_tokens` | Cada resposta "custa" 610 tokens |
   | `test_timeout` | Relógio falso que pula para 999 s |
   | `test_max_tokens_resposta_cortada` | `stop_reason="max_tokens"` |
   | `test_erro_da_api_nao_derruba_o_programa` | O cliente levanta `ConnectionError` |

3. **[`test_sdk_agent.py`](../tests/test_sdk_agent.py)**: mesma ideia para o SDK. Com `monkeypatch`, trocamos a função `query` do SDK
   por uma falsa. A fixture `_sem_claude_code_real` garante que nenhum teste chame o Claude Code de verdade por engano.

> 🎯 **Lição:** testes de agente testam as **decisões do seu código** (parar? continuar? que id devolver?), não a inteligência do modelo.

---

### 3.5 [`src/agent_loop/sdk_agent.py`](../src/agent_loop/sdk_agent.py): o mesmo agente com o Agent SDK

**Ideia principal:** aqui o `while` é do SDK. Nosso trabalho é **configurar** as guardas.

**Compare com o `raw_loop.py`:**

| Guarda | No `raw_loop.py` | No `sdk_agent.py` |
|---|---|---|
| Máximo de voltas | `guard.before_iteration()` | `max_turns=...` (o SDK para sozinho) |
| Custo | `guard.record_usage()` | `max_budget_usd=0.50` |
| Timeout | `guard.before_iteration()` | `async with asyncio.timeout(...)` |
| Chamada repetida | `guard.check_tool_call()` no loop | **Hook `PreToolUse`** |
| Erros seguidos | `guard.record_tool_result()` no loop | `on_tool_result` + hook `PreToolUse` |

**Leia e procure:**

1. **`ClaudeAgentOptions`**: cada opção é uma decisão de segurança:
   - `tools=[]`: **desliga** as tools embutidas do Claude Code (ler/escrever arquivos, shell, web). Nosso agente só pode usar as nossas 3 tools.
   - `allowed_tools=sdk_tool_names()` + `permission_mode="dontAsk"`: as nossas tools rodam sem pedir permissão; **qualquer outra é negada**.
   - `setting_sources=[]`: não carrega seu `CLAUDE.md` nem configurações pessoais, então o agente se comporta igual em qualquer máquina.

2. **Hooks**: funções que o SDK chama em momentos específicos. `PreToolUse` roda **antes** de cada tool e pode **vetar** a chamada:
   ```python
   return {
       "continue_": False,                       # encerra o agente
       "hookSpecificOutput": {
           "hookEventName": "PreToolUse",
           "permissionDecision": "deny",          # bloqueia ESTA tool
           "permissionDecisionReason": "...",     # o Claude lê o motivo
       },
   }
   ```
   Devolver `{}` = "pode seguir".

3. **`nonlocal stop_override`**: o hook é uma função *dentro* de `run_sdk_agent`. Quando ele bloqueia, anota o motivo
   em `stop_override` para o resultado final dizer **qual** guarda disparou.

4. **`async for message in query(...)`**: o SDK entrega mensagens conforme acontecem:
   `AssistantMessage` (texto ou pedido de tool) e, no fim, `ResultMessage` (o resumo: `subtype`, `num_turns`, `usage`).

5. **`except ResultError`**: um detalhe descoberto **testando de verdade**. Quando `max_turns` estoura, o SDK primeiro
   entrega o `ResultMessage` e **depois** levanta uma exceção. Sem esse tratamento, o motivo aparecia como `error`
   genérico em vez de `max_iterations`.
   > 🎯 **Lição:** teste com o sistema real, não só com mocks. Os mocks só simulam o que você *acha* que acontece.

6. **`async`/`await`**: o SDK é assíncrono (conversa com o processo do Claude Code sem travar). Por isso a função é `async def`
   e o `main.py` usa `asyncio.run(...)`.

**❓ Perguntas:**
- O que aconteceria se tirássemos `tools=[]`?
- Por que o hook tem `matcher=f"^mcp__{SDK_SERVER_NAME}__"`?
- Qual a diferença entre `permissionDecision: "deny"` e `continue_: False`?

---

### 3.6 [`src/agent_loop/main.py`](../src/agent_loop/main.py): a linha de comando

Arquivo simples: usa `argparse` para ler as opções, monta os `Limits`, chama o modo escolhido e imprime o resultado.

- O comando `agent` existe por causa de `[project.scripts]` no `pyproject.toml`: `agent = "agent_loop.main:main"`.
- O resumo `[parada: ...]` vai para o **stderr** e a resposta para o **stdout**. Assim dá para salvar só a resposta num arquivo: `uv run agent "..." > resposta.txt`.
- O código de saída é `0` se completou e `1` se parou por uma guarda. Scripts e CI usam isso para saber se deu certo.

✅ **Checkpoint:** desenhe num papel o fluxo do `raw_loop.py` (pode usar o diagrama do [README](../README.md) como base) sem olhar o código.

---

## Parte 4: Rodar tudo, passo a passo

Sempre a partir da pasta do projeto (Parte 1, Passo 1).

### 4.1 Testes

```powershell
# Todos os testes
uv run pytest

# Com o nome de cada teste (-v = verbose)
uv run pytest -v

# Só um arquivo
uv run pytest tests/test_termination.py -v

# Só um teste específico
uv run pytest tests/test_raw_loop.py::test_timeout -v

# Testes cujo nome contém uma palavra
uv run pytest -k repetida -v
```

> 🧪 **Experimento:** abra `termination.py`, troque `>=` por `>` em `check_tool_call`, rode `uv run pytest` e veja quais
> testes falham e por quê. Depois desfaça (`git checkout src/agent_loop/termination.py`).

### 4.2 O agente de verdade (modo SDK, usa sua assinatura)

```powershell
# Pergunta simples
uv run agent "Quanto é 17*23 e que horas são em São Paulo?"

# -v mostra o transcript: cada tool chamada e cada texto
uv run agent -v "Qual o status do chamado INC0002?"

# Usar um modelo menor e mais rápido (gasta menos da sua cota)
uv run agent --model haiku "Quanto é (15+5)*3?"
```

**Chamados que existem na base fictícia:** `INC0001`, `INC0002`, `REQ0003`.

### 4.3 Forçar cada guarda na prática

| Comando | O que você deve ver | Guarda |
|---|---|---|
| `uv run agent --model haiku --max-turns 1 "Quanto é 17*23 e que horas são?"` | `[parada: max_iterations ...]` | Máximo de voltas |
| `uv run agent --model haiku --timeout 1 "Quanto é 17*23?"` | `[parada: timeout ...]` | Timeout |
| `uv run agent -v --model haiku "Qual o status do INC9999 e do INC0002?"` | A tool falha no INC9999, o Claude **se recupera** e termina com `completed` | Erro de tool como `is_error` |

> ℹ️ Com `--max-turns 1`, o resumo pode mostrar `voltas: 2`: o SDK conta os turnos do jeito dele (`num_turns`).
> O que importa é o **motivo** (`max_iterations`).

> ℹ️ As guardas de chamada repetida e de erros seguidos são difíceis de provocar com um modelo bem comportado,
> e é justamente por isso que elas são testadas com o cliente falso (4.1).

**Conferir o código de saída** (PowerShell):

```powershell
uv run agent --model haiku --max-turns 1 "Quanto é 2+2 e que horas são?"
$LASTEXITCODE    # 1 = parou por guarda; 0 = completou
```

### 4.4 Modo raw (opcional, precisa de créditos de API)

Só se um dia você tiver uma API key com créditos em [console.anthropic.com](https://console.anthropic.com):

```powershell
uv add anthropic
$env:ANTHROPIC_API_KEY = "sua-chave-aqui"   # nunca coloque a chave no código nem no Git!
uv run agent --mode raw "Quanto é 17*23?"
```

Sem créditos, você estuda o modo raw pelos testes (4.1). Ele foi feito para isso.

---

## Parte 5: Exercícios práticos

Faça em ordem crescente de dificuldade. Para cada um: **escreva o teste primeiro**, veja falhar, implemente, veja passar.

Crie uma branch para não mexer na `main`:

```powershell
git checkout -b exercicios
```

### ⭐ Exercício 1: Adicionar um chamado fictício
Adicione `INC0004` em `FAKE_TICKETS` (`tools.py`) e pergunte ao agente sobre ele.
*Aprende:* como os dados chegam ao modelo.

### ⭐ Exercício 2: Mudar o system prompt
Em `raw_loop.py`, mude `SYSTEM_PROMPT` para o agente responder sempre em tópicos, ou sempre em inglês. Rode no modo SDK e compare.
*Aprende:* o system prompt define o comportamento geral.

### ⭐⭐ Exercício 3: Uma tool nova
Crie `word_count(text)`, que conta as palavras de um texto:
1. Escreva a função em `tools.py`.
2. Registre um `ToolSpec` no dicionário `TOOLS`, com uma boa `description`.
3. Escreva testes em `test_tools.py`.
4. Rode: `uv run agent -v "Quantas palavras tem a frase 'o rato roeu a roupa do rei'?"`

*Aprende:* como uma tool nova chega automaticamente às duas implementações.
*Dica:* o teste `test_tools_sao_enviadas_para_a_api` vai quebrar. Por quê? Atualize-o.

### ⭐⭐ Exercício 4: Uma guarda nova: máximo de chamadas de tool no total
Nenhuma guarda limita o **total** de tools usadas. Adicione:
1. Em `StopReason`: `MAX_TOOL_CALLS = "max_tool_calls"`
2. Em `Limits`: `max_total_tool_calls: int = 8`
3. Em `TerminationGuard.check_tool_call`: conte todas as chamadas e pare quando passar do limite.
4. Teste em `test_termination.py` **e** em `test_raw_loop.py`.

*Aprende:* o ciclo completo de uma guarda. E, como o `sdk_agent` usa o mesmo `check_tool_call`, ela passa a valer lá também!

### ⭐⭐⭐ Exercício 5: Log de auditoria com `PostToolUse`
No `sdk_agent.py`, adicione um hook `PostToolUse` que imprime `[audit] <tool> <input>` depois de cada tool.
*Aprende:* hooks de observabilidade.
*Dica:* veja a [documentação de hooks](https://code.claude.com/docs/en/agent-sdk/hooks).

### ⭐⭐⭐ Exercício 6: Parar quando a resposta for cortada e pedir para continuar
Hoje, `max_tokens` para o loop. Mude o `raw_loop.py` para, na **primeira** vez que isso acontecer, adicionar uma mensagem
`user` "continue de onde parou" e seguir. Teste com o `FakeClient`.
*Aprende:* recuperação de falhas versus desistir.

Ao terminar, faça commit e envie a branch:

```powershell
git add -A
git commit -m "exercícios do guia de estudo"
git push -u origin exercicios
```

---

## Parte 6: Conexão com a prova CCA-F

Domínio: **Agentic Architecture & Orchestration**. Marque o que você consegue explicar **sem consultar**:

- [ ] O ciclo `messages.create` → `tool_use` → executar → `tool_result` → repetir
- [ ] Que todo `tool_use` exige um `tool_result` com o mesmo `tool_use_id`, na mensagem `user` seguinte
- [ ] Que várias tools pedidas na mesma resposta são respondidas numa **única** mensagem `user`
- [ ] Os valores de `stop_reason` e o que fazer em cada um (principalmente `max_tokens` ≠ sucesso)
- [ ] Por que erros de tool devem voltar como `is_error: true` em vez de quebrar o programa
- [ ] Pelo menos 4 guardas de safe termination e o risco que cada uma evita
- [ ] Por que a `description` da tool importa (é o que guia a escolha do modelo)
- [ ] Por que nunca confiar no input de uma tool (ex.: `eval`)
- [ ] O que o Agent SDK oferece: loop pronto, `max_turns`, `max_budget_usd`, hooks, permissões, MCP in-process
- [ ] Hook `PreToolUse` com `permissionDecision: "deny"` versus `continue_: False`
- [ ] Princípio do menor privilégio: `tools=[]` + `allowed_tools` + `permission_mode="dontAsk"`
- [ ] Como testar agentes de forma determinística (cliente falso / injeção de dependência)
- [ ] A diferença entre autenticar com API key (produto) e com login de assinatura (uso pessoal)

---

## Parte 7: Glossário

| Termo | Significado |
|---|---|
| **Agente** | Programa em que o modelo decide os próximos passos e usa tools em loop até terminar |
| **Agentic loop** | O `while` que alterna "chamar o modelo" e "executar tools" |
| **Tool** | Função que o modelo pode pedir para executar; descrita por nome, descrição e JSON Schema |
| **`tool_use`** | Bloco da resposta em que o modelo pede uma tool |
| **`tool_result`** | Bloco que você devolve com o resultado da tool |
| **`stop_reason`** | Por que o modelo parou de gerar a resposta |
| **Safe termination** | Garantir que o loop sempre acaba, com um motivo explícito |
| **Guarda** | Regra que interrompe o loop (voltas, tempo, custo, repetição...) |
| **Token** | Pedaço de texto (~¾ de palavra); é a unidade de custo e de limite |
| **System prompt** | Instruções gerais que definem o comportamento do modelo |
| **Messages API** | A API "crua" do Claude (`client.messages.create`) |
| **Agent SDK** | Biblioteca que roda o motor do Claude Code como um agente programável |
| **MCP** | *Model Context Protocol*: padrão para expor tools e dados a modelos |
| **MCP in-process** | Servidor MCP que roda dentro do seu próprio programa Python |
| **Hook** | Função que o SDK chama num evento (ex.: antes de uma tool) e que pode bloquear ou alterar a ação |
| **Mock / fake** | Objeto falso que imita um real, para testes |
| **Injeção de dependência** | Receber algo (ex.: o `client`) como parâmetro em vez de criar lá dentro, o que facilita os testes |
| **`uv`** | Ferramenta que gerencia o Python, as dependências e o ambiente virtual |
| **`.venv`** | Ambiente virtual: pasta com as bibliotecas só deste projeto |

---

## Parte 8: Problemas comuns

| Sintoma | Causa | Solução |
|---|---|---|
| `Failed to authenticate: OAuth session expired` | O login do Claude Code expirou | `claude auth login` |
| `"loggedIn": false` em `claude auth status` | O Claude Code de terminal não está logado (o app desktop tem login separado) | `claude auth login` |
| `uv : The term 'uv' is not recognized` | uv não instalado ou fora do PATH | Instale: `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` e abra um terminal novo |
| `gh : The term 'gh' is not recognized` | O terminal foi aberto antes da instalação | Abra um terminal novo, ou use `& "C:\Program Files\GitHub CLI\gh.exe"` |
| `ZoneInfoNotFoundError` / "Fuso horário desconhecido" | O Windows não traz a base de fusos | Já resolvido pela dependência `tzdata`; rode `uv sync` |
| O caminho com espaço dá erro | `lab claude` tem espaço | Use aspas: `cd "...\lab claude\..."` |
| `[parada: error ...]` no modo SDK | Veja a mensagem logo abaixo | Normalmente é login; rode com `-v` para mais detalhes |
| Warning `LF will be replaced by CRLF` no commit | Diferença de fim de linha Windows/Linux | Inofensivo, pode ignorar |
