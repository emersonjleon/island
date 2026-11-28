# Edades de la Isla — propuesta de diseño

Propuesta del 19 de noviembre de 2026, pedida por Emerson; segunda versión con sus
respuestas del mismo día. Todavía no hay código. Cuando se cierren las preguntas
del final, la parte de reglas pasa en inglés a `docs/GAME_DESIGN.md` y los
paquetes de trabajo a un plan de etapa.

## Resumen

Cada jugador sube de edad por su cuenta, como en Age of Empires: paga un costo
que siempre incluye **pescado**, espera un tiempo de "investigación" mientras el
juego sigue, y al llegar desbloquea construcciones, desarrollos mejorados,
pequeñas ventajas y puntos. Hay tres edades:

| Edad | Nombre | Se llega | Desbloquea (por defecto) |
| --- | --- | --- | --- |
| I | Edad de los Colonos | al empezar | caminos, asentamientos, ciudades, desarrollos de nivel I |
| II | Edad del Mar | pagando y con 1 ciudad | **+1 punto**, desarrollos de nivel II, +1 pescado por edificio pesquero, límite del ladrón +1, construcción 15 % más rápida |
| III | Edad Dorada | pagando, desde la II y con 2 ciudades | **+2 puntos**, megaciudades, desarrollos de nivel III, construcción 30 % más rápida |

Las edades suman hasta 3 puntos, así que están pensadas para **partidas con metas
más altas** (Isla grande con 12 y Enorme con 14). **Clásica y Rápida juegan sin
edades**, como hoy.

Todo número de este documento es un ajuste con su valor por defecto, editable en
la partida Personalizada (sección nueva "Edades" del editor de todos los ajustes)
y guardable en códigos y configuraciones.

## Decisiones de Emerson (19 nov 2026)

- Edades apagadas en Clásica.
- Edad del Mar da 1 punto y Edad Dorada 2; se usan para metas de puntos más altas.
- Sin Maravilla.
- Puerto 2:1 de pescado: sin decidir (ver "El pescado").
- Modo premium: Personalizada y las partidas de más de 4 jugadores (Isla grande y
  Enorme) son solo para premium. Por ahora todos son premium (ver "Modo premium").
- Sin preset gratis de 4 jugadores con edades por ahora.
- Un jugador gratis entra a partidas premium solo invitado: cada premium tiene 3
  invitados fijos para todas sus partidas y 15 invitaciones sueltas al mes. No se
  muestra hasta que el modo premium se active.

## Por qué así

- **Le da un uso al pescado.** Hoy el pescado se produce desde el inicio pero solo
  lo pide el colono extra (etapa 3). Con las edades, las zonas de pesca pasan a
  ser lugares buscados en la colocación inicial, y el pescado se vuelve el
  "alimento" que hace crecer a la civilización, como la comida en Age of Empires.
- **Las megaciudades dejan de ser solo un parche.** Hoy existen para que una isla
  llena no se trabe. Al pedir la Edad Dorada se vuelven una meta de final de
  partida, que se ve venir.
- **Es una decisión en tiempo real.** Subir de edad cuesta un poco más que una
  ciudad. Cada jugador decide si expandirse ahora o invertir para crecer más
  rápido después, y todos ven quién está subiendo.
- **Encaja con lo que ya hay.** Es un estado por jugador, un comando nuevo y
  unas puertas en reglas que ya existen (construcción, producción, ladrón,
  desarrollos). No cambia el tablero ni el reloj.

## Cómo se sube de edad

1. **Requisitos.** Para pedir la edad siguiente el jugador necesita la edad
   anterior y un mínimo de edificios. Por defecto: Edad II no pide ciudades (antes 1, cambiado por la simulación de WP28); Edad III
   pide 2 ciudades (las megaciudades cuentan como ciudades). También hay un mínimo
   de puntos, apagado por defecto (0).
2. **Pago.** Se paga todo al empezar, como una construcción.
3. **Investigación.** Una barra de progreso en el panel del jugador. Dura 30 s para
   la II y 45 s para la III (3 y 4–5 tiradas en Isla grande). Mientras tanto el
   jugador produce, construye, comercia y juega cartas con normalidad. Solo puede
   haber una subida en curso por jugador.
4. **Cancelar.** Se puede cancelar y se devuelve `build.refund_pct` del costo
   (100 % por defecto), igual que una construcción.
5. **Llegada.** Un aviso para todos: "Ana entró en la Edad del Mar", y los puntos
   se suman en ese momento (si llegan a la meta, gana). La edad es información
   pública, incluso con niebla.
6. **No se pierde.** Sin guerra, una edad alcanzada es para siempre.

No hace falta un colono para subir de edad, tampoco en la variación Colonos
(WP23): la investigación ocurre en las ciudades que ya pide el requisito.

## Costos por defecto

Emerson (24 nov 2026): subir de edad cuesta uno de cada recurso de tierra más
2 pescados (Edad del Mar) o 3 (Edad Dorada). La Edad III da 2 puntos (25 nov).

| Qué | Costo | Cartas | Tiempo |
| --- | --- | --- | --- |
| Subir a Edad II | 1 madera, 1 ladrillo, 1 lana, 1 grano, 1 mineral, 2 pescado | 7 | 30 s |
| Subir a Edad III | 1 madera, 1 ladrillo, 1 lana, 1 grano, 1 mineral, 3 pescado | 8 | 45 s |
| Desarrollo nivel I (actual) | 1 lana, 1 grano, 1 mineral | 3 | — |
| Desarrollo nivel II | 1 lana, 1 grano, 1 mineral, 1 pescado | 4 | — |
| Desarrollo nivel III | 1 lana, 1 grano, 1 mineral, 2 pescado | 5 | — |
| Megaciudad (25 nov 2026) | 1 madera, 1 ladrillo, 2 grano, 1 mineral, 1 pescado | 6 | 15 s |

Como referencia, una ciudad cuesta 5 cartas y vale 1 punto más que un
asentamiento. Subir a la II vale 1 punto por 6 cartas; subir a la III vale 2
puntos por 8. Por punto, las edades cuestan algo menos que una ciudad, pero piden
pescado y esperar, y la III además pide dos ciudades antes. Esa diferencia es la
que hay que confirmar con la simulación (ver "Balance").

## Desbloqueos

### Construcciones

Un mapa `ages.unlock` dice qué edad pide cada construcción. Por defecto: camino,
asentamiento y ciudad en la I; megaciudad en la III. El anfitrión puede, por
ejemplo, poner la ciudad en la II para una partida más lenta, o la megaciudad en
la II para una más corta.

El panel de construcción muestra lo bloqueado con un candado y "Requiere Edad III".
Intentar construirlo da el error `age.locked`.

Con las edades apagadas (Clásica), las megaciudades siguen libres como hoy.

### Ventajas pasivas de cada edad

Se suman al llegar. Todas son ajustes por edad (`ages.age2.bonus.*`, `ages.age3.bonus.*`):

| Ventaja | Edad II | Edad III | Para qué |
| --- | --- | --- | --- |
| Puntos de victoria | +1 | +2 | Las edades son un camino a la victoria en metas altas |
| Pescado extra por edificio en zona de pesca, cuando esa zona produce | +1 | +1 | Las edades se pagan con pescado; quien lo invierte produce más |
| Límite de cartas ante el 7 | +1 (8) | +2 (9) | Permite ahorrar para costos grandes sin perderlo todo con el ladrón |
| Tiempo de construcción | 85 % | 70 % | Sensación de civilización más avanzada |
| Piezas extra en la reserva | 0 | 0 | Opción para islas grandes (p. ej. +1 asentamiento) |
| Alcance de vista (vista creciente) | 0 | 0 | Opción que se conecta con el trabajo de la etapa 3 |
| Colonos máximos (variación Colonos) | 0 | 0 | Opción |

## Desarrollos mejorados

*Rediseño del 25 nov 2026. La primera propuesta tenía cartas demasiado fuertes
para un juego en tiempo real. Los cambios y sus razones están en "Qué cambió y
por qué", al final de esta sección.*

### La idea

Hoy hay un solo mazo de desarrollos (14 caballeros, 5 puntos, 2 construcción de
caminos, 2 año de abundancia, 2 monopolio), que cuesta lana, trigo y mineral.
Las edades agregan **dos mazos más, uno por edad**. Las cartas viejas no cambian:
el nivel I es el mazo de hoy.

- Al comprar, el jugador elige de qué mazo, hasta el de su edad. Un jugador en la
  Edad Dorada puede seguir comprando nivel I si le conviene (es más barato).
- Cada nivel cuesta lo de hoy más pescado: el nivel II, +1 pescado (4 cartas), y
  el nivel III, +2 pescados (5 cartas).
- Sigue valiendo la regla de una carta jugada por tirada, compartida entre los
  niveles. La carta comprada se puede jugar desde la tirada siguiente.
- Cada mazo se rellena solo cuando se acaba (`dev_cards.refill`), como hoy.
- Los demás ven tu mano como hoy: cuántas cartas tienes, y ahora también de qué
  nivel, pero no cuáles.

### Reglas del diseño

Las cartas se diseñaron con cinco reglas. Sirven también para juzgar cartas nuevas
en el futuro:

1. **Nada instantáneo.** En tiempo real, el corazón del juego es la carrera por
   un lugar: quien empieza a construir primero se arriesga a que otro termine
   antes. Ninguna carta se salta el tiempo de construcción.
2. **Poder parecido al precio.** Una carta de nivel I vale unas 3 cartas. Una de
   nivel II puede valer unas 4 y una de nivel III unas 5, pero no mucho más. El
   pescado es escaso, así que se pagan con algo que cuesta conseguir.
3. **Ataques con tope.** Una carta de ataque afecta a un solo jugador y nunca
   roba más de 2 cartas. Roba 2 solo a quien acumula por encima de su límite
   del 7, así que ahorrar sin pasarse sigue siendo seguro. Así no se castiga a
   quien junta pescado para subir de edad.
4. **Todo efecto se ve.** Los efectos que duran varias tiradas se muestran a
   todos, con su cuenta regresiva.
5. **Los puntos no son una lotería.** Comprar cartas para buscar puntos no debe
   rendir más que construir. Hoy, en el nivel I, sale un punto cada 15 cartas
   gastadas en promedio. Una ciudad da un punto por 5 cartas. Los niveles altos
   no bajan de esas 15 cartas por punto.

### Nivel II: desarrollos del Mar (18 cartas)

El mazo del mar y del comercio: acelera la economía, con poco ataque y pocos puntos.

| Carta | Copias | Qué hace | Cuándo conviene | Contrajuego |
| --- | --- | --- | --- | --- |
| **Caballero veterano** | 6 | Como el caballero, pero mueve el ladrón hasta 4 hexágonos (el normal, 3). Roba 1 carta, o 2 si la víctima tiene más cartas que su límite del 7. Cuenta como 1 caballero para el Mayor Ejército. | Para llegar a un rival lejano o castigar a quien acumula. | No pasarse del límite del 7; tener edificios en varias zonas. |
| **Flota pesquera** | 3 | Durante las 3 tiradas siguientes, cada uno de tus edificios en una zona de pesca da 1 pescado más cuando esa zona produce. | Antes de ahorrar para la Edad Dorada o para vender pescado. | El ladrón en tu zona de pesca. |
| **Mercader** | 3 | Durante las 3 tiradas siguientes, comercias con el banco a 2:1 en cualquier recurso. | Cuando tienes mucho de un recurso y te falta otro. | Dura poco; los demás ven que está activo. |
| **Calzada** | 2 | 3 caminos gratis, con el tiempo normal de construcción (la construcción de caminos da 2). | Para correr hacia un lugar libre o pelear el Camino más largo. | Llegar primero; las reglas normales de los caminos. |
| **Cosecha abundante** | 2 | Tomas 3 recursos del banco, a lo sumo 1 de ellos pescado (el año de abundancia da 2). | Para completar un costo justo. | Si el banco no tiene, no se da. |
| **Punto de victoria** | 2 | 1 punto, al jugarla. | Siempre. | — |

Proporciones: 6 caballeros de 18 (33 %; hoy son 14 de 25, el 56 %) y 2 puntos de
18 (11 %). Eso es un punto cada 36 cartas gastadas: nadie compra el nivel II para
buscar puntos, sino por su economía.

### Nivel III: desarrollos Dorados (13 cartas)

El mazo del final de la partida. Da herramientas para cerrar la partida, pero
también una para alcanzar al líder.

| Carta | Copias | Qué hace | Cuándo conviene | Contrajuego |
| --- | --- | --- | --- | --- |
| **Caballero de élite** | 4 | Mueve el ladrón hasta 5 hexágonos y roba como el veterano (1 carta, o 2 si la víctima pasa su límite). **Cuenta como 2 caballeros** para el Mayor Ejército. | Para pelear el Mayor Ejército al final. | Otro jugador en la Edad Dorada puede responder igual. |
| **Arquitecto** | 2 | En las 5 tiradas siguientes, tu próxima ciudad o megaciudad cuesta 2 cartas menos (eliges cuáles, sin contar el pescado). Se construye con el tiempo normal. | Antes de una megaciudad. | Si otro termina antes en ese lugar, el descuento se pierde con la obra. |
| **Gran mercado** | 2 | Durante las 5 tiradas siguientes, comercias con el banco a 2:1 en cualquier recurso. | Para convertir una gran producción en megaciudades. | Los demás ven que está activo. |
| **Tributo** | 2 | Cada jugador con más puntos que tú te da 1 carta al azar. | Cuando vas atrás. Si vas primero, no hace nada. | Ninguno: es el freno al líder. |
| **Punto de victoria** | 3 | 1 punto, al jugarla. | Siempre. | — |

Proporciones: 3 puntos de 13 (23 %). A 5 cartas cada compra, sale un punto cada
22 cartas, menos que en el nivel I (15). El nivel III se compra por sus efectos y
no para buscar puntos.

**Por qué el Tributo.** El riesgo más grande de las edades es la bola de nieve:
quien llega primero a la Dorada produce más y suma puntos. El Tributo es la única
carta que pesa más cuanto más atrás estás. Para el líder no hace nada, así que no
se puede usar para escaparse.

### Efectos que duran varias tiradas

Flota pesquera, Mercader, Gran mercado y Arquitecto duran un tiempo. Se muestran
como un ícono con cuenta regresiva en el panel del jugador, y los demás ven que
está activo (un Mercader activo dice "este jugador va a comerciar"). Para
mantenerlo simple, cada jugador tiene a lo sumo un efecto activo de cada carta.
Jugar otra igual suma sus tiradas a la cuenta, hasta el doble de la duración de
una carta.

### Ajustes de los desarrollos mejorados

Todo es configurable en Personalizada:

- El contenido de cada mazo (`dev_cards.deck_tier2`, `dev_cards.deck_tier3`). Un
  mazo con todas las copias en 0 apaga ese nivel.
- Su costo (`economy.costs.dev_card_tier2`, `dev_card_tier3`).
- Cada número de cada carta:
  - el alcance y el robo de los caballeros, y cuántos caballeros cuenta el de élite;
  - las tiradas de cada efecto y su máximo;
  - el pescado de la Flota;
  - las cartas y el pescado máximo de la Cosecha;
  - los caminos de la Calzada;
  - el descuento del Arquitecto;
  - las cartas del Tributo.

### Qué cambió y por qué

| Carta (primera propuesta) | Ahora | Por qué |
| --- | --- | --- |
| Caballero veterano: 8 copias, 5 hexágonos, roba 2 siempre | 6 copias, 4 hexágonos, roba 2 solo a quien pasa su límite | Sumado al ladrón del 7, castigaba a quien ahorra pescado para subir de edad |
| Caballero de élite: cualquier hexágono, roba 2, cuenta 2, 5 copias | 5 hexágonos, roba como el veterano, cuenta 2, 4 copias | Con dos cartas se ganaba el Mayor Ejército en segundos desde cualquier lado |
| Gran calzada: 3 caminos al instante | Calzada: 3 caminos con tiempo normal | Construir al instante deja a los demás sin respuesta en la carrera por un lugar |
| Arquitecto: al instante y 2 cartas menos | Solo 2 cartas menos, en 5 tiradas | Igual que la calzada; la ventana de 5 tiradas evita guardarlo toda la partida |
| Flota pesquera: el doble de pescado | +1 pescado por edificio | El doble se sumaba con la ventaja de la Edad II y desbordaba el banco de pescado |
| Cosecha abundante: 3, pescado incluido | 3, a lo sumo 1 pescado | Daba 3 pescados por 1, y el pescado dejaba de ser escaso |
| Gran mercado: 2:1 con el banco y 1:1 en puertos de un recurso | 2:1 con el banco en todo, 5 tiradas | El 1:1 casi no se ve en el juego y era difícil de explicar |
| Monopolio real (dos monopolios a la vez) | Quitado; en su lugar, el Tributo | Al final de la partida dejaba sin nada a todos a la vez |
| Puntos: 3 de 20 (II) y 5 de 15 (III) | 2 de 18 y 3 de 13 | El final se volvía una compra de cartas para buscar puntos |

### Cómo se comprueba

Antes de fijar los números, una tanda de partidas de bots (`engine/sim`), con y
sin desarrollos mejorados, debe cumplir esto:

- La partida no se alarga ni se acorta más de un 10 %.
- El lado que usa las edades sigue ganando entre el 50 % y el 65 %.
- El jugador que va primero a mitad de partida no gana más seguido que hoy (la bola de nieve).
- El Mayor Ejército no cambia de manos más de 3 veces por partida en la mediana.
- Ninguna carta decide sola: ganar con o sin cada carta no cambia más de 10 puntos porcentuales.

Si un criterio falla, se cambian los números de las cartas (copias, robo,
tiradas), no las reglas.

## El pescado

Hoy hay 6 zonas de pesca (fichas 4, 5, 6, 8, 9 y 10, unos 24 puntos de
probabilidad en total) y 19 cartas de pescado en el banco. En Isla grande hay
más zonas y más banco. Con uno o dos edificios por zona, la isla produce unos
50–70 pescados por partida de 60 tiradas, unos 15 por jugador si están
repartidos. Las edades piden 5 y los desarrollos mejorados 1–2 cada uno, así que
alcanza, pero quien no toque el mar depende del comercio.

Lo que ayuda a que el pescado no decida la partida desde la colocación inicial:

- La ventaja de +1 pescado de la Edad II.
- El comercio entre jugadores: el pescado se vuelve algo que se negocia.
- Cosecha abundante, que puede dar 1 pescado.
- Los bots valoran las zonas de pesca cuando hay edades, así que compiten por ellas.

**El puerto 2:1 de pescado (sin decidir).** A favor: le da a quien no tiene zona
de pesca una forma de conseguirlo sin depender de otros. En contra: quien tenga
ese puerto y además una zona de pesca puede volverse muy fuerte, y el pescado
deja de ser escaso. Mi recomendación ahora es **no agregarlo por defecto** (ya es
un ajuste: `board.harbors.specific.fish`, hoy 0) y decidir con la simulación: si
los jugadores sin mar llegan a la Edad del Mar mucho más tarde, se agrega.

Interacciones que salen solas: el monopolio de pescado se vuelve una jugada fuerte
contra quien está ahorrando para subir de edad, y el ladrón en una zona de pesca
(`robber.may_enter_fishing`, etapa 3) frena a un rival que va adelante.

## Balance en tiempo real

Objetivo en Isla grande (tiradas de 10 s, meta de 12 puntos):

| Momento | Tirada | Minuto |
| --- | --- | --- |
| Primeras ciudades | 8–15 | 1–3 |
| Primeros en la Edad del Mar | 12–20 | 2–4 |
| Primeros en la Edad Dorada | 30–40 | 5–7 |
| Primera megaciudad | 35–45 | 6–8 |
| Fin de la partida | 60–75 | 10–13 |

Las edades suman 3 de los 12 o 14 puntos, una parte importante pero no la mitad.
Una partida que ignore las edades debe poder ganar, pero le cuesta más. Las
cifras de costos y tiempos son un primer cálculo. Se ajustan con la simulación
que ya existe (`engine/sim`): partidas con bots que siguen distintas estrategias
(ignorar las edades, subir pronto, subir tarde), midiendo cuándo llega cada
edad, la duración de la partida y quién gana. Un criterio razonable es que la
estrategia de edades gane entre el 50 % y el 65 % contra la que las ignora, con
bots de igual nivel.

### Resultado de la simulación (WP28, 23 nov 2026)

Bots "codiciosos" (los de `engine/sim`), que suben de edad apenas pueden y
comercian con el banco por lo que les falta. "Mitad" significa que los asientos
pares usan las edades y los impares las ignoran; "gana" es el porcentaje de
partidas que gana el lado de las edades. Las tiradas son la mediana; los bots
juegan más lento que una persona (unas 85–105 tiradas por partida en vez de 60–75).

| Costos (II / III) | Ciudades pedidas (II / III) | Preset | Primera Edad II (todos) | Gana (mitad) |
| --- | --- | --- | --- | --- |
| 6 cartas / 8 cartas (diseño original) | 1 / 2 | Edades | tirada 68 (14 de 20 partidas) | 50 % |
| 6 / 8 (original) | 1 / 2 | Grande con edades | tirada 84 | 60 % |
| 4 / 6 | 0 / 2 | Edades | tirada 14 | 68 % |
| 4 / 6 | 1 / 2 | Edades | tirada 42 | 58 % |
| **5 / 6 (elegido)** | **0 / 2** | Edades | **tirada 14** | **62 %** |
| **5 / 6 (elegido)** | **0 / 2** | Grande con edades | **tirada 23** | **63 %** |

Con los costos originales casi nadie llegaba a la Edad del Mar antes del final:
la ciudad que pedía llegaba tarde y el pescado se gastaba en otras cosas. Sin
la ciudad y con 5 cartas, la Edad II llega en el primer sexto de la partida,
como pedía la tabla de arriba, y el lado de las edades gana el 62–63 % (dentro
del 50–65 % buscado). La Edad III sigue llegando tarde (en la mitad de las
partidas), sobre todo porque los bots priorizan construir; vale la pena mirarla
de nuevo cuando los bots tengan niveles (WP28 completo con `engine/ai`). El
puerto 2:1 de pescado no hizo falta para estos números.

### Cambios de Emerson (23 nov 2026)

- La Edad II vuelve a pedir una ciudad; la Edad III da 3 puntos (antes 2).
- Producción extra por edad: queda como ajuste (`ages.ageN.bonus.extra_per_settlement`
  / `extra_per_city`), en 0 por defecto; los edificios producen como en Clásica.
- El rescate con pescado (`robber.fish_ransom`, 2 en los presets con edades) solo
  protege desde la Edad II (`ages.fish_ransom_age`).
- Colonos (variación Colonos con edades): recogen desde la Edad II
  (`ages.settler_gather_age`) y alejan al ladrón desde la Edad III
  (`ages.settler_guard_age`).
- Metas: Edades 14 puntos, Grande con edades 17.

### Cambios de Emerson (24 y 25 nov 2026)

- Subir de edad cuesta uno de cada recurso de tierra más 2 pescados (Edad del Mar)
  o 3 (Edad Dorada).
- La Edad III vuelve a dar 2 puntos.
- Premio **Mayor población**: 2 puntos para quien tenga **más colonos** (mínimo 3),
  en toda partida con colonos que se quedan tras la colocación, con o sin edades;
  funciona como el Camino más largo (`settlers.largest_population`, antes
  `ages.largest_population`; la migración de ajustes v1 → v2 mueve los puntos).

Con esos valores, partidas de bots: Edades dura unas 87 tiradas (78 en Clásica)
y el lado de las edades gana el 53 %; Grande con edades dura unas 100 tiradas (92
en Isla grande) y el lado de las edades gana el 56 %. La primera Edad II llega más tarde (tirada 50–80) porque vuelve a pedir una
ciudad.

Riesgo de "bola de nieve": quien llega primero a la Dorada produce más y suma 2
puntos. Contrapesos ya incluidos: la subida se anuncia y tarda, el monopolio y el
ladrón pueden frenar el pescado, el Caballero veterano alcanza más lejos, y el
Tributo del nivel III le quita cartas a quien va adelante. Si la
simulación muestra que el líder se escapa, hay un ajuste opcional
`ages.followers_discount_pct`: cada jugador que ya está en una edad abarata un
X % la subida para los demás (apagado por defecto).

Presets:

| Preset | Edades | Meta | Premium |
| --- | --- | --- | --- |
| Clásica | no | 10 | no |
| Rápida | no | 7 | no |
| Isla grande (5–6 jugadores) | sí | 12 | sí |
| Enorme (7 o más) | sí | 14 | sí |
| Personalizada | lo que elija el anfitrión | la que elija | sí |

Por ahora no hay un preset gratis de 4 jugadores con edades (decisión de Emerson):
en una mesa de 4 las edades se juegan en Personalizada.

## Modo premium

### Qué es premium

| Función | Gratis | Premium |
| --- | --- | --- |
| Clásica y Rápida (hasta 4 jugadores) | sí | sí |
| Isla grande y Enorme (más de 4 jugadores) | no | sí |
| Personalizada (todos los ajustes, configuraciones guardadas) | no | sí |
| Unirse a una partida premium creada por otro | solo invitado | sí |

La regla la aplica el servidor, no solo la pantalla: es el **anfitrión** quien
necesita premium para crear la partida.

**Invitados.** Un jugador gratis entra a una partida premium solo con invitación
del anfitrión. Cada jugador premium tiene dos tipos de invitación (decisión de
Emerson):

- **Invitados fijos: 3.** Una lista de hasta 3 personas que pueden entrar a
  todas sus partidas premium, sin gastar nada. Se puede cambiar cuando quiera
  (ajuste del sitio `PREMIUM_FIXED_GUESTS = 3`).
- **Invitaciones sueltas: 15 al mes.** Cada una deja entrar a un jugador gratis a
  una partida. Se pueden usar varias en la misma partida. Se renuevan cada mes y
  no se acumulan (ajuste `PREMIUM_MONTHLY_INVITES = 15`).

Detalles de la propuesta:

- La invitación suelta se gasta cuando el invitado ocupa el asiento, no al
  mandarla; si la partida se cancela antes de empezar, se devuelve.
- Un invitado fijo nunca gasta invitaciones sueltas.
- El mes es el mes calendario (se renueva el día 1).
- Modelos `lobby.PremiumGuest` (anfitrión, invitado) para la lista fija y
  `lobby.GuestInvite` (anfitrión, invitado, partida, fecha) para las sueltas.
- La invitación se manda desde la sala, con la lista de amigos que ya existe en
  el chat.
- Al unirse, el servidor revisa: la partida es premium y el jugador no lo es →
  debe ser invitado fijo o tener una invitación suelta para esa partida; si no,
  error `lobby.premium_invite_required`. Si al anfitrión no le quedan invitaciones,
  error `lobby.premium_no_invites_left`.
- **No se muestra todavía:** mientras `PREMIUM_FOR_ALL = True`, las listas, el
  contador y los mensajes no aparecen en ninguna pantalla.

Los códigos y enlaces de configuración siguen la misma regla: crear una partida
desde un código de Personalizada, o con más de 4 jugadores, pide premium.

### Cómo se implementa (sin activarlo todavía)

- Un campo en el usuario, `accounts.User.premium_until` (fecha, vacía = no
  premium), y una propiedad `is_premium`.
- Un ajuste del sitio `PREMIUM_FOR_ALL = True` en `config/settings`. Mientras esté
  en `True`, todos son premium y nada cambia para nadie. Para activar el modo
  premium se cambia a `False`, sin tocar código.
- Una función `lobby.premium.can_create(user, preset, overrides)` usada por la
  vista de crear partida, por "crear desde enlace", por el cambio de ajustes en la
  sala antes de empezar y por "Jugar ya". Error con código `lobby.premium_required`
  y un mensaje en español e inglés.
- En la pantalla de crear partida, las opciones premium muestran una etiqueta
  "Premium" y, si el usuario no lo es, quedan deshabilitadas con una explicación.
- El administrador de Django permite dar premium a un usuario a mano. Pagos y
  suscripciones quedan para después.
- Los bots no cuentan: una mesa de 4 con bots sigue siendo gratis.

Esto es un paquete de trabajo propio, independiente de las edades (WP31 abajo).

## Bots

Los tres niveles aprenden a subir de edad con reglas simples, sin cambiar su forma
de pensar:

- **Fácil:** sube a la II cuando ya puede pagarla y tiene una ciudad; casi nunca
  compra desarrollos mejorados; rara vez llega a la III.
- **Medio:** trata la subida como una construcción más en su lista de objetivos,
  que vale 1 o 2 puntos. Sube a la II después de su segunda ciudad, a la III
  cuando le alcanza, y comercia por el pescado que le falta. Compra nivel II o III
  cuando tiene el pescado de sobra.
- **Difícil:** valora las zonas de pesca al colocar sus primeros asentamientos,
  sube a la II apenas puede, guarda pescado para la III, juega Flota pesquera y
  Mercader cuando le rinden, usa el Arquitecto para su megaciudad, juega el
  Tributo cuando va atrás y no compra nivel III solo para buscar puntos.

Esto se agrega como campos del perfil de cada nivel en `engine/ai/levels.py`
(`age_eagerness`, `fish_bonus`), que son parámetros del bot y no reglas del juego.

*Hecho (24 nov 2026):* campos `max_age`, `age_trades` y `fishing_bonus` en
`BotLevel`. Fácil sube solo a la Edad del Mar y sin comerciar por ella; medio y
difícil suben hasta la Dorada y comercian por lo que les falta. Valorar las zonas
de pesca al colocar (`fishing_bonus`) empeoró al difícil en las simulaciones (ganó
12 de 30 contra el medio con 3 puntos por zona, 15 de 30 sin ellos), así que queda
en 0. En el preset Edades, mesa de 2: difícil gana 55 de 90 contra medio y 14 de 20
contra fácil; medio gana 15 de 20 contra fácil.

## Ajustes nuevos (resumen)

Un grupo nuevo `ages` en `GameSettings`, con edades en ranuras fijas (`age2`,
`age3`) para que el editor de la partida Personalizada las muestre sin cambios
especiales (solo maneja números, interruptores, opciones y mapas):

```
ages.enabled                      no en Clásica y Rápida; sí en Isla grande y Enorme
ages.unlock                       {road: 1, settlement: 1, city: 1, megacity: 3}
ages.dev_tiers                    sí (desarrollos mejorados)
ages.followers_discount_pct       0
ages.age2 / ages.age3:
    cost                          mapa de recursos (ver tabla de costos)
    time_ms                       30000 / 45000
    requires.cities               1 / 2
    requires.points               0 / 0
    bonus.points                  1 / 2
    bonus.fish_per_fishing_building   1 / 1
    bonus.card_limit              1 / 1   (se acumula: 8 y 9)
    bonus.build_time_pct          85 / 70
    bonus.pieces                  mapa {settlements, roads, cities, megacities}
    bonus.sight                   0 / 0
    bonus.settlers_max            0 / 0
economy.costs.dev_card_tier2 / dev_card_tier3
dev_cards.deck_tier2 / deck_tier3 y los números de cada carta nueva
```

Compatibilidad: con `ages.enabled = false` todo queda como hoy (megaciudades
libres, un solo mazo). Como las edades vienen apagadas en Clásica, los códigos
viejos de Clásica, Rápida y Personalizada no cambian. Los de Isla grande y Enorme
pasarían a tener edades; para evitarlo, `schema_version` pasa a 2 y la migración
de la versión 1 agrega `ages.enabled = false`.

## Interfaz

- Una insignia con el número romano de la edad junto al nombre de cada jugador,
  en el panel y en la lista de puntos.
- Un botón "Subir de edad" en el panel de construcción, con el costo, los puntos
  que da, los requisitos que faltan y luego la barra de progreso con "Cancelar".
- Candados en lo bloqueado, con la edad que lo desbloquea.
- Avisos para todos al empezar y al terminar una subida.
- En la compra de desarrollos, una pestaña por nivel con su costo.
- Íconos con cuenta regresiva para Flota pesquera, Mercader y Gran mercado.
- Estadísticas y fin de partida: "Edades" como fuente de puntos en la leyenda, y
  la tirada en que cada jugador llegó a cada edad. (Hecho: una tabla con el
  minuto de juego en que cada jugador llegó a la Edad II y III, y una marca con
  el número de la edad sobre su línea en la gráfica de puntos. Se usa el minuto
  y no la tirada porque la gráfica ya va por tiempo.)
- Opcional: los edificios cambian de aspecto con la edad (2D y 3D). (Hecho en 2D:
  un banderín sobre el techo más alto, crema en la Edad II y dorado con cola
  partida en la Edad III; nada en la Edad I ni sin edades.)
- Todo el texto en español e inglés.

## Paquetes de trabajo propuestos

Siguen la numeración después de la etapa 3 (WP19–WP25). Uno por PR, cada uno deja
el juego jugable.

1. **WP26 Edades en el motor.** Ajustes `ages`, estado por jugador en
   `state.ext["ages"]`, comandos `advance_age` y `cancel_age`, eventos
   `AgeAdvanceStarted`, `AgeAdvanceCancelled`, `AgeReached`, errores `age.*`,
   puertas en construcción, ventajas pasivas, puntos y la migración a la versión
   2 del esquema. Pruebas deterministas con semillas.
   *Hecho (22 nov 2026):* `engine/rules/ages.py` y `age_state.py`. Las ventajas que
   se suman (puntos, pescado, límite del 7) se acumulan entre edades; el tiempo de
   construcción usa el de la edad más alta. Ningún preset activa las edades todavía
   (eso llega con la interfaz, WP27), así que no hace falta migrar el esquema: los
   códigos ya no existen y las configuraciones guardadas no cambian.
2. **WP27 Interfaz de edades.** Insignia, botón, barra, candados, avisos,
   estadísticas, etiquetas del editor y la regla rápida "Edades".
3. **WP28 Bots y balance.** Reglas de los bots y una tanda de simulaciones para
   fijar costos, tiempos y el puerto de pescado; los valores finales vuelven a
   este documento.
   *Primera parte hecha (23 nov 2026):* el bot codicioso sube de edad y comercia
   por el costo; costos nuevos en "Resultado de la simulación".
4. **WP29 Desarrollos mejorados**, en dos partes:
   - **WP29a.** Mazos por nivel y compra por nivel, con las cartas de economía
     (Flota pesquera, Mercader, Gran mercado, Calzada, Cosecha abundante,
     Arquitecto y puntos). Incluye los efectos por tiradas, en motor, interfaz y bots.
   - **WP29b.** Las cartas de ataque y de freno (Caballero veterano, Caballero de
     élite, Tributo) y la tanda de simulaciones de "Cómo se comprueba".
5. **WP31 Modo premium.** Campo y ajuste del sitio, la regla en todas las formas
   de crear partida, etiquetas en la pantalla y el administrador. Se puede hacer
   antes o en paralelo con las edades.

WP26 a WP28 ya dan un juego completo con edades y megaciudades.

## Alternativas descartadas

- **Edades globales** (toda la isla avanza con el reloj). Más simple, pero quita
  la decisión de cada jugador, que es lo interesante.
- **Mejorar las cartas que ya se tienen** al subir de edad, en vez de mazos por
  nivel. Más difícil de entender y de mostrar.
- **Pagar la edad solo con pescado.** Haría que la colocación inicial junto al mar
  decida la partida.
- **Maravilla.** Descartada por Emerson.

## Preguntas abiertas para Emerson

Ya respondidas: preset gratis de 4 con edades (por ahora no); jugadores gratis en
partidas premium (sí: 3 invitados fijos y 15 invitaciones sueltas al mes).

1. Desarrollos mejorados: rediseñados el 25 nov 2026, por pedido de Emerson, para
   que sean menos disruptivos. ¿Te gusta el rediseño, sobre todo el Tributo?
2. Puerto 2:1 de pescado: propongo decidirlo con la simulación. ¿De acuerdo?
3. ¿Tres edades, o cuatro con una "Edad de los Navegantes" reservada para barcos y
   combate más adelante? Propongo tres ahora.
4. ¿Las ciudades siguen en la Edad I (como Catan)? Propongo que sí.
5. ¿Te gustan los nombres (Colonos, Mar, Dorada)?
6. ¿Las edades de los demás siempre visibles, incluso con niebla? Propongo que sí.
