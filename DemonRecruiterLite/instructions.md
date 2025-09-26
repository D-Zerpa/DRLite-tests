# Ejercicios – Demon Recruitment (SMT-lite) en Python (POO)

En este ejercicio crearás un simulador simplificado de **reclutamiento de demonios** inspirado en SMT, usando clases y métodos.  
El usuario tendrá un **Jugador** con un alineamiento y negociará con distintos **Demonios**. En cada turno, el demonio formula una **pregunta**; las respuestas modificarán el **alineamiento del jugador** (postura) y el **rapport** de la sesión.  
Si la **distancia de alineamiento** entre jugador y demonio es lo bastante baja **y** el **rapport** es suficiente, el demonio se **une**; si la distancia es demasiado grande o se agota la **paciencia**, el demonio **huye**.

---

## Clases

### 1) Clase `Alignment`
Define la clase `Alignment` que tendrá lo siguiente:

**Define el método `__init__()`** que tome dos enteros opcionales (`law_chaos=0`, `light_dark=0`) y haga lo siguiente:
- Inicializa el atributo `law_chaos` en el valor recibido (rango recomendado `-5..5`).
- Inicializa el atributo `light_dark` en el valor recibido (rango recomendado `-5..5`).

**Define el método `clamp()`** (sin parámetros) que:
- Limite `law_chaos` y `light_dark` al rango `-5..5`.
- No retorna nada.

**Define el método `distancia_manhattan(otro)`** que:
- Calcule y retorne `abs(self.law_chaos - otro.law_chaos) + abs(self.light_dark - otro.light_dark)`.

---

### 2) Clase `Question`
Define la clase `Question` que tendrá lo siguiente:

**Define el método `__init__()`** que tome:
- `id` (string), `text` (string),
- `choices` (diccionario con claves = etiquetas de respuesta y valores = efectos como dict: `{"dLC": int, "dLD": int, "dRapport": int}`),
- `tags` (lista de strings).
Y que haga lo siguiente:
- Inicializa los atributos `id`, `text`, `choices` y `tags` con los valores recibidos.

*(Nota: esta clase actúa como contenedor de datos; no requiere más métodos en esta fase.)*

---

### 3) Clase `Demon`
Define la clase `Demon` que tendrá lo siguiente:

**Define el método `__init__()`** que tome:
- `name` (string),
- `alignment` (objeto `Alignment`),
- `personality` (string de entre: `"PLAYFUL"`, `"CHILDISH"`, `"MOODY"`, `"CUNNING"`, `"PROUD"`),
- y que además inicialice los siguientes parámetros por defecto:
  - `patience = 4` (turnos de negociación),
  - `tolerance = 3` (distancia máxima aceptable),
  - `rapport_needed = 2` (umbral mínimo para unirse).
Y que haga lo siguiente:
- Inicializa todos esos atributos en el objeto.
- Inicializa el atributo `disponible` en `True` (sirve para marcar si ya fue reclutado).

**Define el método `pick_question(session)`** (sin parámetros adicionales) que:
- Seleccione **una pregunta** del pool disponible, preferiblemente que **coincida** con alguno de los `tags` valorados por la `personality` (en esta fase, puedes seleccionar **al azar**; la afinidad por personalidad se introducirá más adelante).
- Retorne el objeto `Question` elegido.

**Define el método `reaccionar(choice_effect)`** que:
- Reciba el diccionario de efectos de la elección del jugador (por ejemplo `{"dLC": +1, "dLD": 0, "dRapport": +1}`).
- Retorne una **tupla** con dos enteros: `(delta_rapport, delta_tolerance)` donde:
  - En esta fase, `delta_rapport` será exactamente `choice_effect["dRapport"]`.
  - `delta_tolerance` será `0` (lo ajustarás por personalidad en fases posteriores).

---

### 4) Clase `Player`
Define la clase `Player` que tendrá lo siguiente:

**Define el método `__init__()`** que tome:
- `core_alignment` (objeto `Alignment`; tendencia real del jugador),
- y que haga lo siguiente:
  - Inicializa el atributo `core_alignment` con el valor recibido.
  - Inicializa el atributo `stance_alignment` como **copia** de `core_alignment` (postura durante la negociación).
  - Inicializa el atributo `roster` como una lista vacía (demonios reclutados).

**Define el método `relajar_postura(step=1)`** (sin parámetros obligatorios) que:
- Modifique `stance_alignment` **acercándolo** a `core_alignment` en **1 punto por eje** (si `stance` es menor que `core` en un eje, súmale 1; si es mayor, réstale 1; si es igual, no cambies).
- Aplique `clamp()` a `stance_alignment` al final.

---

### 5) Clase `NegotiationSession`
Define la clase `NegotiationSession` que tendrá lo siguiente:

**Define el método `__init__()`** que tome:
- `player` (objeto `Player`),
- `demon` (objeto `Demon`),
- `questions_pool` (lista de objetos `Question`),
y que haga lo siguiente:
- Inicializa los atributos `player`, `demon`, `questions_pool`.
- Inicializa el atributo `rapport` en `0` (elige un rango y sé consistente; recomendado `-3..+3`).
- Inicializa `turns_left` con `demon.patience`.
- Inicializa `en_curso` en `True`.
- Inicializa `reclutado` en `False` y `huido` en `False`.
- Inicializa `ronda` en `1`.

**Define el método `preguntar()`** (sin parámetros) que haga lo siguiente:
- Obtén una `Question` llamando a `self.demon.pick_question(self)`.
- Muestra por pantalla el texto de la pregunta y sus opciones **enumeradas**.
- Solicita al usuario **una opción** válida.
- Obtén el `choice_effect` asociado a esa opción.

**Define el método `procesar_respuesta(choice_effect)`** que:
- **Aplique** a `player.stance_alignment` los deltas `dLC` y `dLD`.
- Aplique `clamp()` a `player.stance_alignment`.
- Llame a `self.demon.reaccionar(choice_effect)` y **sume** el `delta_rapport` al `self.rapport`.
- Limite `self.rapport` al rango elegido (ej. `-3..+3`).
- **Decremente** `self.turns_left` en `1`.
- Llame a `player.relajar_postura()` (para acercar `stance` a `core`).
- Imprima un resumen de cambios (alineamiento, rapport, turnos restantes).

**Define el método `mostrar_valores()`** (sin parámetros) que:
- Muestre por pantalla el estado actual de la sesión:
  - `ronda`, `turns_left`, `rapport`,
  - `player.stance_alignment` (ambos ejes),
  - `demon.name`, `demon.alignment` y la **distancia Manhattan** entre jugador (stance) y demonio.

**Define el método `dificultad(nivel)`** que tome un entero entre `1` y `5` y haga lo siguiente:
- **Aumente la presión de la sesión** de forma aleatoria leve:
  - Disminuya `rapport` **aleatoriamente** entre `0` y `nivel//2` (sin ir por debajo del mínimo).
  - (Opcional simple) Desplace `stance_alignment` **1 paso aleatorio lejos** del demonio **con probabilidad** `nivel/10`.  
- Aplique `clamp()` y actualice los valores mostrados si corresponde.

**Define el método `comprobar_union()`** (sin parámetros) que:
- Calcule la **distancia** Manhattan entre `player.stance_alignment` y `demon.alignment`.
- Si `distancia <= demon.tolerance` **y** `rapport >= demon.rapport_needed`:
  - Imprima que el demonio está dispuesto a unirse.
  - Cambie `reclutado` a `True`.
  - Cambie `en_curso` a `False`.

**Define el método `comprobar_fuga()`** (sin parámetros) que:
- Calcule la **distancia** Manhattan entre `player.stance_alignment` y `demon.alignment`.
- Si `distancia > demon.tolerance + 2` **o** `turns_left <= 0`:
  - Imprima que el demonio pierde el interés y se marcha.
  - Cambie `huido` a `True`.
  - Cambie `en_curso` a `False`.

**Define el método `finalizar_union()`** (sin parámetros) que:
- Si `reclutado` es `True`:
  - Agregue el `demon` al `player.roster`.
  - Cambie `demon.disponible` a `False`.
  - Imprima un mensaje de éxito.

**Define el método `finalizar_fuga()`** (sin parámetros) que:
- Si `huido` es `True`:
  - Imprima un mensaje de despedida/fracaso.

---

## Funciones (nivel consola)

**Define la función `mostrar_menu(session)`** que tome un parámetro (`session`) objeto de `NegotiationSession` y haga lo siguiente:
- Si `session.en_curso` es `True`, **Imprimir**:
  ```
  ¿Qué deseas hacer?
  1) Responder la siguiente pregunta
  2) Bromear (minijuego rápido para ajustar rapport)
  3) Mostrar estado de la sesión
  4) Intentar cerrar trato ahora (evaluar unión)
  5) Despedirse (terminar negociación)
  ```
  - Tome por pantalla la opción del usuario (`opcion`) y **retorne** el string `opcion`.
- Si `session.en_curso` es `False`:
  - Imprima: `La negociación ha terminado...`
  - Retorne el string `"0"` (o el valor que decidas para indicar fin).

**Define la función `llamar_accion(session, opcion)`** que tome dos parámetros (`session`, `opcion` string) y haga lo siguiente:
- Si `opcion` es `"1"`:
  - Llame a `session.preguntar()`.
  - Llame a `session.procesar_respuesta(...)` con el `choice_effect` obtenido.
- Si `opcion` es `"2"` (**minijuego**):
  - Genere un número aleatorio entre `0` y `2`.
  - Pida al usuario adivinar un número entre `0` y `2`.
  - Si acierta: **aumente** `rapport` en `2` (sin exceder el máximo) e imprima `¡Correcto!`.
  - Si falla: **disminuya** `rapport` en `1` (sin exceder el mínimo) e imprima `Incorrecto.`.
- Si `opcion` es `"3"`:
  - Llame a `session.mostrar_valores()`.
- Si `opcion` es `"4"`:
  - Llame a `session.comprobar_union()`.
- Si `opcion` es `"5"`:
  - Cambie `session.en_curso` a `False`.
  - Cambie `session.huido` a `True` e imprima que el demonio se marcha.
- Si `opcion` no es válida:
  - Imprima: `OPCION NO VALIDA`.

---

## Código Principal

**Imprime** un mensaje con el nombre del proyecto y otro que lo describa.  
(Ej.: *“SMT-lite Demon Recruitment – Negocia con demonios usando alineamiento y rapport (POO)”*)

---

**Inicializa** los **datos del prototipo**:
- Crea el `player` con `core_alignment = Alignment(0, 0)` y `stance_alignment` igual al core; `roster` vacío.
- Crea una **lista de demonios** (mínimo 2) con sus `alignment`, `personality`, y parámetros por defecto o los que definas.
- Crea un **pool de preguntas** (4–6) con `choices` y `tags` variados.
- (Opcional) fija una **semilla aleatoria** para depuración.

---

**Pide** al usuario el **nivel de dificultad**, número entre `1` y `5`, y guárdalo como entero en la variable `nivel_dificultad`.

---

**Selecciona** un demonio disponible para negociar (por índice o al azar) y asigna la referencia a la variable `demon_actual`.

---

**Inicializa** un objeto `NegotiationSession` con `(player, demon_actual, questions_pool)` y asígnalo a `sesion`.

---

**Inicializa** una variable `ronda` e iguálala a `1`.

---

**Crea** un bucle `while` que se ejecute **mientras** `sesion.en_curso` sea `True`:
- Imprime: `Esta es la ronda número {ronda}.`
- Llama a `sesion.mostrar_valores()`.
- Llama a la función `mostrar_menu(sesion)` y guarda el retorno en `opcion`.
- Llama a la función `llamar_accion(sesion, opcion)`.
- Llama a `sesion.comprobar_union()`.
- Llama a `sesion.comprobar_fuga()`.
- (Opcional) Detén la ejecución **3 segundos**.
- Llama a `sesion.dificultad(nivel_dificultad)`.
- **Incrementa** en `1` la variable `ronda`.

---

**Si** `sesion.reclutado` es `True`:
- Llama a `sesion.finalizar_union()`.

**Si** `sesion.huido` es `True`:
- Llama a `sesion.finalizar_fuga()`.

---

**Imprime** un resumen:
- Alineamiento final del jugador (core y postura).
- Distancia final a `demon_actual`.
- Si fue reclutado o huyó.
- Número total de rondas jugadas en la sesión.
- **Roster** actual del jugador.

---

## Reglas de dificultad y límites (mantén consistencia)

- Aplica `clamp()` al alineamiento **después de cada cambio**.
- El `rapport` debe permanecer en el rango que definas (ej. `-3..+3`).
- `turns_left` debe **decrementar** en cada turno (o por `procesar_respuesta`).
- **Unión** requiere **dos condiciones**: `distancia <= tolerance` **y** `rapport >= rapport_needed`.
- **Fuga** si `distancia > tolerance + 2` **o** si `turns_left == 0`.
- El minijuego **nunca** debe empujar `rapport` fuera de su rango.
- Mensajes claros en consola explicando cada cambio.

---

## Datos mínimos sugeridos (para testear rápidamente)

- Demonio A: `name = "Pixie"`, `alignment = (LC=+1, LD=+2)`, `personality = "PLAYFUL"`, `tolerance = 4`, `patience = 5`, `rapport_needed = 2`.
- Demonio B: `name = "Onmoraki"`, `alignment = (LC=−2, LD=−2)`, `personality = "MOODY"`, `tolerance = 3`, `patience = 4`, `rapport_needed = 2`.
- 4–6 preguntas con `choices` de efectos pequeños (−1..+1) y `tags` variados (`mercy`, `order`, `freedom`, `ruthless`, `honor`, `pragmatism`, `humor`, …).

---

## (Opcional) Extensiones — **No implementar ahora**
- Personalidad afectando `patience`, `tolerance`, `rapport_needed` y **peso de tags** (modulando `dRapport` y hasta `tolerance` dinámicamente).
- Eventos especiales: pedir oro/ítems, respuestas trampa, caprichos.
- Persistencia (JSON/SQLite) del `player` y su `roster`.
- Capa Discord con sesiones por `user_id` y comandos `/negotiate`.