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
2 pescados (Edad del Mar) o 3 (Edad Dorada).

| Qué | Costo | Cartas | Tiempo |
| --- | --- | --- | --- |
| Subir a Edad II | 1 madera, 1 ladrillo, 1 lana, 1 grano, 1 mineral, 2 pescado | 7 | 30 s |
| Subir a Edad III | 1 madera, 1 ladrillo, 1 lana, 1 grano, 1 mineral, 3 pescado | 8 | 45 s |
| Desarrollo nivel I (actual) | 1 lana, 1 grano, 1 mineral | 3 | — |
| Desarrollo nivel II | 1 lana, 1 grano, 1 mineral, 1 pescado | 4 | — |
| Desarrollo nivel III | 1 lana, 1 grano, 1 mineral, 2 pescado | 5 | — |
| Megaciudad (sin cambio) | 3 grano, 4 mineral, 2 ladrillo, 2 lana | 11 | 15 s |

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

### La idea

Hoy hay un solo mazo de desarrollos (14 caballeros, 5 puntos, 2 construcción de
caminos, 2 año de abundancia, 2 monopolio). La propuesta agrega **dos mazos más,
uno por edad**. Las cartas viejas no cambian: el nivel I es el mazo de hoy.

- Al comprar, el jugador elige de qué mazo, hasta el de su edad. Un jugador en la
  Edad Dorada puede seguir comprando nivel I si le conviene (es más barato).
- Cada nivel cuesta lo mismo que hoy más pescado: nivel II +1 pescado, nivel III
  +2 pescados.
- Se mantiene la regla de una carta jugada por tirada, compartida entre niveles,
  y la carta comprada se puede jugar desde la tirada siguiente.
- Cada mazo se rellena solo cuando se acaba (`dev_cards.refill`), como hoy.
- Lo que hay en tu mano se ve igual que hoy para los demás: cuántas tienes, y
  ahora también de qué nivel (no cuáles).

### Por qué mazos por nivel

Un mazo de nivel más alto no es solo "cartas más fuertes": cambia **qué** sale.
El nivel II es el mazo del mar y del comercio (pescado, intercambio, caminos), y
el nivel III es el mazo del final de partida (ejército, megaciudades y puntos).
Así comprar un desarrollo es una decisión: nivel I barato y conocido, nivel II
para acelerar la economía, nivel III para cerrar la partida.

Otra opción era que subir de edad mejorara las cartas que ya tienes (por ejemplo,
que todos tus caballeros roben 2). Es más difícil de explicar en pantalla y de
equilibrar, y no le da uso al pescado al comprar. Por eso la descarto.

### Nivel II: desarrollos del Mar (20 cartas)

| Carta | Copias | Qué hace | Cuándo conviene | Contrajuego |
| --- | --- | --- | --- | --- |
| **Caballero veterano** | 8 | Mueve el ladrón hasta 5 hexágonos (el caballero normal, 3) y roba 2 cartas en vez de 1. Cuenta como 1 caballero para el Mayor Ejército. | Para frenar al líder aunque esté lejos, o para quitar pescado a quien ahorra para subir de edad. | Gastar antes de acumular; tener edificios en varias zonas. |
| **Flota pesquera** | 3 | Durante las 3 tiradas siguientes, tus edificios en zonas de pesca producen el doble (suma con el +1 de la Edad II). | Cuando estás por subir a la Dorada o quieres vender pescado en el tablero de ofertas. | El ladrón en tu zona de pesca (si `robber.may_enter_fishing` está activo). |
| **Mercader** | 2 | Durante las 3 tiradas siguientes, comercias con el banco a 2:1 en cualquier recurso. | Cuando tienes muchas cartas de un tipo y te falta otro para una ciudad o una edad. | Ninguno directo; dura poco. |
| **Gran calzada** | 2 | 3 caminos gratis, construidos al instante (sin tiempo de construcción). | Para ganarle un lugar a otro jugador o asegurar el Camino más largo. | Llegar primero; los caminos siguen la regla de distancia normal. |
| **Cosecha abundante** | 2 | Tomas 3 recursos cualesquiera del banco, pescado incluido (el año de abundancia da 2). | Para completar un costo justo, sobre todo el pescado de una edad. | Si el banco no tiene, no se da. |
| **Punto de victoria** | 3 | 1 punto, al jugarla. | Siempre. | — |

Proporción: 8 caballeros de 20 (40 %, como hoy 14 de 25 es 56 %) y 3 puntos de 20
(15 %, como hoy 20 %). El nivel II es menos de ejército y más de economía.

### Nivel III: desarrollos Dorados (15 cartas)

| Carta | Copias | Qué hace | Cuándo conviene | Contrajuego |
| --- | --- | --- | --- | --- |
| **Caballero de élite** | 5 | Mueve el ladrón a cualquier hexágono, roba 2 cartas y **cuenta como 2 caballeros** para el Mayor Ejército. | Para ganar o arrebatar el Mayor Ejército al final de la partida. | Otro jugador en la Dorada puede responder igual. |
| **Arquitecto** | 2 | Tu próxima ciudad o megaciudad se construye al instante y cuesta 2 cartas menos (eliges cuáles). | Justo antes de una megaciudad, para cerrar la partida antes de que reaccionen. | Ninguno directo. |
| **Gran mercado** | 2 | Durante las 5 tiradas siguientes, comercias con el banco a 2:1 y con tus puertos a 1:1 en un recurso que eliges al jugarla. | Para convertir una gran producción de un recurso en megaciudades. | Ninguno directo. |
| **Monopolio real** | 1 | Como el monopolio, pero de dos recursos a la vez. | Cuando todos acumulan para el final. | Gastar antes de acumular. |
| **Punto de victoria** | 5 | 1 punto, al jugarla. | Siempre. | — |

Proporción: 5 puntos de 15 (33 %). El nivel III es la vía de puntos de final de
partida: con 5 pescados y 10 cartas más se compran dos desarrollos de nivel III,
con dos tercios de probabilidad de al menos un punto.

### Efectos que duran varias tiradas

Flota pesquera, Mercader y Gran mercado son los primeros efectos del juego que
duran un tiempo. Encajan con el tiempo real: se muestran como un ícono con cuenta
regresiva en el panel del jugador, y los demás ven que está activo (un Mercader
activo dice "este jugador va a comerciar"). Para mantenerlo simple, solo puede
haber un efecto activo de cada carta por jugador; jugar otra igual alarga la
duración en vez de duplicarla.

### Ajustes de los desarrollos mejorados

Todo es configurable en Personalizada: el contenido de cada mazo
(`dev_cards.deck_tier2`, `dev_cards.deck_tier3`), su costo
(`economy.costs.dev_card_tier2`, `dev_card_tier3`), y cada número de cada carta
(distancia y robo de los caballeros, cuántos caballeros cuenta el de élite, tiradas
de cada efecto, cartas de cada cosecha, caminos de la gran calzada, descuento del
arquitecto). Un mazo con todas las copias en 0 apaga ese nivel.

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
- Cosecha abundante, que puede dar pescado.
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
- Premio **Mayor población** (solo con edades y colonos que se quedan tras la colocación): 2 puntos para quien tenga la mayor
  población (poblado 1, ciudad 2, megaciudad 4), con un mínimo de 6; funciona como
  el Camino más largo (`ages.largest_population`).
- Metas: Edades 14 puntos, Grande con edades 17.

Con esos valores, partidas de bots: Edades dura unas 87 tiradas (78 en Clásica)
y el lado de las edades gana el 53 %; Grande con edades dura unas 100 tiradas (92
en Isla grande) y el lado de las edades gana el 56 %. La primera Edad II llega más tarde (tirada 50–80) porque vuelve a pedir una
ciudad.

Riesgo de "bola de nieve": quien llega primero a la Dorada produce más y suma 2
puntos. Contrapesos ya incluidos: la subida se anuncia y tarda, el monopolio y el
ladrón pueden frenar el pescado, y el Caballero veterano alcanza más lejos. Si la
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
  Mercader cuando le rinden, usa el Arquitecto para su megaciudad y compra nivel
  III cerca del final para buscar puntos.

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
  la tirada en que cada jugador llegó a cada edad.
- Opcional: los edificios cambian de aspecto con la edad (2D y 3D).
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
4. **WP29 Desarrollos mejorados.** Mazos por nivel, cartas nuevas y efectos por
   tiradas, en motor, interfaz y bots.
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

1. ¿Te gustan los desarrollos mejorados propuestos? ¿Alguna carta que quieras
   agregar, quitar o cambiar?
2. Puerto 2:1 de pescado: propongo decidirlo con la simulación. ¿De acuerdo?
3. ¿Tres edades, o cuatro con una "Edad de los Navegantes" reservada para barcos y
   combate más adelante? Propongo tres ahora.
4. ¿Las ciudades siguen en la Edad I (como Catan)? Propongo que sí.
5. ¿Te gustan los nombres (Colonos, Mar, Dorada)?
6. ¿Las edades de los demás siempre visibles, incluso con niebla? Propongo que sí.
