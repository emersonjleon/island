# Edades de la Isla — propuesta de diseño

Propuesta del 19 de noviembre de 2026, pedida por Emerson. Todavía no hay código.
Cuando se aprueben las decisiones de la sección final, la parte de reglas pasa en
inglés a `docs/GAME_DESIGN.md` y los paquetes de trabajo a un plan de etapa.

## Resumen

Cada jugador sube de edad por su cuenta, como en Age of Empires: paga un costo
que siempre incluye **pescado**, espera un tiempo de "investigación" mientras el
juego sigue, y al llegar desbloquea construcciones, desarrollos mejorados y
pequeñas ventajas. Hay tres edades por defecto:

| Edad | Nombre | Se llega | Desbloquea (por defecto) |
| --- | --- | --- | --- |
| I | Edad de los Colonos | al empezar | caminos, asentamientos, ciudades, desarrollos de nivel I |
| II | Edad del Mar | pagando y con 1 ciudad | desarrollos de nivel II, +1 pescado por edificio pesquero, límite del ladrón +1, construcción 15 % más rápida |
| III | Edad Dorada | pagando, desde la II y con 2 ciudades | megaciudades, desarrollos de nivel III, la Maravilla (opcional), +1 punto de victoria, construcción 30 % más rápida |

Todo número de este documento es un ajuste con su valor por defecto, editable en
la partida Personalizada (sección nueva "Edades" del editor de todos los ajustes)
y guardable en códigos y configuraciones.

## Por qué así

- **Le da un uso al pescado.** Hoy el pescado se produce desde el inicio pero solo
  lo pide el colono extra (etapa 3). Con las edades, las zonas de pesca pasan a
  ser lugares buscados en la colocación inicial, y el pescado se vuelve el
  "alimento" que hace crecer a la civilización, como la comida en Age of Empires.
- **Las megaciudades dejan de ser solo un parche.** Hoy existen para que una isla
  llena no se trabe. Al pedir la Edad Dorada se vuelven una meta de final de
  partida, que se ve venir.
- **Es una decisión en tiempo real.** Subir de edad cuesta lo mismo que una ciudad
  o un poco más, y no da puntos inmediatos (salvo la III). Cada jugador decide si
  expandirse ahora o invertir para crecer más rápido después, y todos ven quién
  está subiendo.
- **Encaja con lo que ya hay.** Es un estado por jugador, un comando nuevo y
  unas puertas en reglas que ya existen (construcción, producción, ladrón,
  desarrollos). No cambia el tablero ni el reloj.

## Cómo se sube de edad

1. **Requisitos.** Para pedir la edad siguiente el jugador necesita la edad
   anterior y un mínimo de edificios. Por defecto: Edad II pide 1 ciudad; Edad III
   pide 2 ciudades (las megaciudades cuentan como ciudades). También hay un mínimo
   de puntos, apagado por defecto (0).
2. **Pago.** Se paga todo al empezar, como una construcción.
3. **Investigación.** Una barra de progreso en el panel del jugador. Dura 30 s para
   la II y 45 s para la III (2 y 3 tiradas en Clásica). Mientras tanto el jugador
   produce, construye, comercia y juega cartas con normalidad. Solo puede haber una
   subida en curso por jugador.
4. **Cancelar.** Se puede cancelar y se devuelve `build.refund_pct` del costo
   (100 % por defecto), igual que una construcción.
5. **Llegada.** Un aviso para todos: "Ana entró en la Edad del Mar". La edad es
   información pública, incluso con niebla, porque es parte de la tensión del juego.
6. **No se pierde.** Sin guerra, una edad alcanzada es para siempre.

No hace falta un colono para subir de edad, tampoco en la variación Colonos
(WP23): la investigación ocurre en las ciudades que ya pide el requisito.

## Costos por defecto

| Qué | Costo | Cartas | Tiempo |
| --- | --- | --- | --- |
| Subir a Edad II | 2 pescado, 2 grano, 1 lana, 1 ladrillo | 6 | 30 s |
| Subir a Edad III | 3 pescado, 2 grano, 2 mineral, 1 lana | 8 | 45 s |
| Desarrollo nivel I (actual) | 1 lana, 1 grano, 1 mineral | 3 | — |
| Desarrollo nivel II | 1 lana, 1 grano, 1 mineral, 1 pescado | 4 | — |
| Desarrollo nivel III | 1 lana, 1 grano, 1 mineral, 2 pescado | 5 | — |
| Megaciudad (sin cambio) | 3 grano, 4 mineral, 2 ladrillo, 2 lana | 11 | 15 s |
| Maravilla (opcional) | 4 pescado, 3 ladrillo, 3 mineral, 2 madera, 2 lana | 14 | 60 s |

Como referencia, una ciudad cuesta 5 cartas. Llegar a la Edad Dorada cuesta 14
cartas y 5 pescados en total.

## Desbloqueos

### Construcciones

Un mapa `ages.unlock` dice qué edad pide cada construcción. Por defecto: camino,
asentamiento y ciudad en la I; megaciudad en la III; Maravilla en la III. El
anfitrión puede, por ejemplo, poner la ciudad en la II para una partida más lenta,
o la megaciudad en la II para una más corta.

El panel de construcción muestra lo bloqueado con un candado y "Requiere Edad III".
Intentar construirlo da el error `age.locked`.

### Desarrollos mejorados

Cada nivel de desarrollos tiene su propio mazo (con la misma regla de rellenado
`dev_cards.refill`). Al comprar, el jugador elige el nivel, hasta el de su edad.
La regla de una carta por tirada se comparte entre niveles. Las cartas de nivel I
siguen como hoy.

| Nivel | Carta | Efecto | Copias |
| --- | --- | --- | --- |
| II | Caballero veterano | Mueve el ladrón hasta 5 hexágonos y roba 2 cartas. Cuenta como 1 caballero para el Mayor Ejército | 8 |
| II | Gran calzada | 3 caminos gratis, construidos al instante | 2 |
| II | Flota pesquera | Durante las 3 tiradas siguientes, tus edificios en zonas de pesca producen el doble | 3 |
| II | Mercader | Durante las 3 tiradas siguientes, comercias con el banco a 2:1 en cualquier recurso | 2 |
| II | Cosecha abundante | Tomas 3 recursos cualesquiera del banco, pescado incluido | 2 |
| II | Punto de victoria | 1 punto | 3 |
| III | Caballero de élite | Mueve el ladrón a cualquier hexágono, roba 2 y cuenta como 2 caballeros | 6 |
| III | Gran mercado | Durante 5 tiradas, banco a 2:1 y puertos a 1:1 en un recurso que eliges | 2 |
| III | Arquitecto | Tu próxima ciudad o megaciudad se construye al instante y cuesta 2 cartas menos (las que elijas) | 2 |
| III | Monopolio real | Como el monopolio, pero de dos recursos | 1 |
| III | Punto de victoria | 1 punto | 4 |

Los efectos "durante N tiradas" son nuevos en el motor y encajan bien con el
tiempo real: se ven como un ícono con cuenta regresiva en el panel. Todos los
números (N, cartas robadas, distancia, copias) son ajustes.

### Ventajas pasivas de cada edad

Se suman al llegar. Todas son ajustes por edad (`ages.age2.bonus.*`, `ages.age3.bonus.*`):

| Ventaja | Edad II | Edad III | Para qué |
| --- | --- | --- | --- |
| Pescado extra por edificio en zona de pesca, cuando esa zona produce | +1 | +1 | Las edades se pagan con pescado; quien lo invierte produce más |
| Límite de cartas ante el 7 | +1 (8) | +2 (9) | Permite ahorrar para costos grandes sin perderlo todo con el ladrón |
| Tiempo de construcción | 85 % | 70 % | Sensación de civilización más avanzada |
| Puntos de victoria | 0 | +1 | Hace de la Edad Dorada un camino real a la victoria |
| Piezas extra en la reserva | 0 | 0 | Opción para islas grandes (p. ej. +1 asentamiento) |
| Alcance de vista (vista creciente) | 0 | 0 | Opción que se conecta con el trabajo de la etapa 3 |
| Colonos máximos (variación Colonos) | 0 | 0 | Opción |

### La Maravilla (opcional)

Una construcción única de la Edad Dorada, sobre una ciudad o megaciudad propia:
14 cartas (4 de pescado), 60 s de construcción, vale 2 puntos. Una por jugador. Su
barra de progreso es visible para todos, así que los demás pueden correr para
ganar antes de que termine. Se apaga con `pieces.wonders = 0`. Propongo
dejarla apagada en Clásica y encendida en Isla grande y Enorme, donde las partidas
son largas.

## El pescado

Hoy hay 6 zonas de pesca (fichas 4, 5, 6, 8, 9 y 10, unos 24 puntos de
probabilidad en total) y 19 cartas de pescado en el banco. Con unos 60 tiros por
partida y uno o dos edificios por zona, la isla produce unos 50–70 pescados por
partida, unos 15 por jugador si están repartidos. Las edades piden 5 y los
desarrollos mejorados 1–2 cada uno, así que alcanza, pero quien no toque el mar
depende del comercio. Por eso propongo:

- **Un puerto 2:1 de pescado** por defecto cuando hay edades (hoy hay 0).
- La ventaja de +1 pescado de la Edad II, para que el pescado no se acabe a
  mitad de partida.
- Dejar el comercio entre jugadores como la vía principal: el pescado se vuelve
  algo que se negocia en el tablero de ofertas.
- Señalar las zonas de pesca en la colocación inicial (los bots las valoran más
  cuando hay edades).

Interacciones que salen solas: el monopolio de pescado se vuelve una jugada fuerte
contra quien está ahorrando para subir de edad, y el ladrón en una zona de pesca
(`robber.may_enter_fishing`, etapa 3) frena a un rival que va adelante.

## Balance en tiempo real

Objetivo en Clásica (tiradas de 15 s, unas 60 tiradas, meta de 10 puntos):

| Momento | Tirada | Minuto |
| --- | --- | --- |
| Primeras ciudades | 8–15 | 2–4 |
| Primeros en la Edad II | 12–20 | 3–5 |
| Primeros en la Edad III | 30–40 | 8–10 |
| Primera megaciudad | 35–45 | 9–11 |
| Fin de la partida | 50–65 | 13–16 |

Una partida sin subir de edad debe poder ganar, pero un poco más tarde; la
diferencia debe venir de la producción extra, no de los puntos. Las cifras de
costos y tiempos de arriba son un primer cálculo. Se ajustan con la simulación
que ya existe (`engine/sim`): partidas con bots que siguen distintas
estrategias (ignorar las edades, subir pronto, subir tarde), midiendo cuándo
llega cada edad, la duración de la partida y quién gana. Un criterio razonable es
que la estrategia de edades gane entre el 45 % y el 60 % contra la que las
ignora, con bots de igual nivel.

Riesgo de "bola de nieve": quien llega primero a la III produce más y además
suma un punto. Contrapesos ya incluidos: la III da solo 1 punto, el monopolio y
el ladrón pueden frenar el pescado, y la subida se anuncia. Si la simulación
muestra que el líder se escapa, hay un ajuste opcional
`ages.followers_discount_pct`: cada jugador que ya está en una edad abarata un
X % la subida para los demás (apagado por defecto).

Presets propuestos:

| Preset | Edades | Diferencias |
| --- | --- | --- |
| Clásica | sí | Valores de este documento, sin Maravilla |
| Rápida | sí | Tiempos de subida 20 s y 30 s; Edad II sin requisito de ciudad |
| Isla grande / Enorme | sí | Maravilla encendida; +1 asentamiento en la reserva en la Edad II |
| Personalizada | lo que elija el anfitrión | Interruptor "Edades" entre las reglas rápidas |

## Bots

Los tres niveles aprenden a subir de edad con reglas simples, sin cambiar su forma
de pensar:

- **Fácil:** sube a la II cuando ya puede pagarla y tiene una ciudad; casi nunca
  compra desarrollos mejorados; rara vez llega a la III.
- **Medio:** trata la subida como una construcción más en su lista de objetivos.
  Sube a la II después de su segunda ciudad, a la III cuando ya no le quedan
  lugares para asentamientos o tiene 7 puntos, y comercia por el pescado que le
  falta.
- **Difícil:** valora las zonas de pesca al colocar sus primeros asentamientos,
  sube a la II apenas puede, guarda pescado para la III, usa Flota pesquera y
  Mercader cuando le rinden, y compra desarrollos de nivel II en vez de nivel I.

Esto se agrega como campos del perfil de cada nivel en `engine/ai/levels.py`
(`age_eagerness`, `fish_bonus`), que son parámetros del bot y no reglas del juego.

## Ajustes nuevos (resumen)

Un grupo nuevo `ages` en `GameSettings`, con edades en ranuras fijas (`age2`,
`age3`) para que el editor de la partida Personalizada las muestre sin cambios
especiales (solo maneja números, interruptores, opciones y mapas):

```
ages.enabled                      sí
ages.unlock                       {road: 1, settlement: 1, city: 1, megacity: 3, wonder: 3}
ages.dev_tiers                    sí (desarrollos mejorados)
ages.followers_discount_pct       0
ages.age2 / ages.age3:
    cost                          mapa de recursos (ver tabla de costos)
    time_ms                       30000 / 45000
    requires.cities               1 / 2
    requires.points               0 / 0
    bonus.fish_per_fishing_building   1 / 1
    bonus.card_limit              1 / 1   (se acumula: 8 y 9)
    bonus.build_time_pct          85 / 70
    bonus.points                  0 / 1
    bonus.pieces                  mapa {settlements, roads, cities, megacities}
    bonus.sight                   0 / 0
    bonus.settlers_max            0 / 0
economy.costs.dev_card_tier2 / dev_card_tier3
dev_cards.deck_tier2 / deck_tier3 y los números de cada carta nueva
pieces.wonders, economy.costs.wonder, build.time_ms.wonder, victory.building_points.wonder
```

Compatibilidad: los códigos y configuraciones guardadas de antes no tienen edades.
`schema_version` pasa a 2 y la migración de la versión 1 agrega
`ages.enabled = false`, así una partida creada con un código viejo se juega igual
que antes. Con las edades apagadas todo queda como hoy (megaciudades libres, un
solo mazo).

## Interfaz

- Una insignia con el número romano de la edad junto al nombre de cada jugador,
  en el panel y en la lista de puntos.
- Un botón "Subir de edad" en el panel de construcción, con el costo, los
  requisitos que faltan y luego la barra de progreso con "Cancelar".
- Candados en lo bloqueado, con la edad que lo desbloquea.
- Avisos para todos al empezar y al terminar una subida.
- En la compra de desarrollos, una pestaña por nivel.
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
2. **WP27 Interfaz de edades.** Insignia, botón, barra, candados, avisos,
   estadísticas, etiquetas del editor y la regla rápida "Edades".
3. **WP28 Bots y balance.** Reglas de los bots y una tanda de simulaciones para
   fijar costos y tiempos; los valores finales vuelven a este documento.
4. **WP29 Desarrollos mejorados.** Mazos por nivel, cartas nuevas y efectos por
   tiradas, en motor e interfaz.
5. **WP30 Maravilla** (si se aprueba).

WP26 a WP28 ya dan un juego completo con edades y megaciudades; WP29 y WP30 se
pueden hacer después o en paralelo con la etapa 3.

## Alternativas descartadas

- **Edades globales** (toda la isla avanza con el reloj). Más simple, pero quita
  la decisión de cada jugador, que es lo interesante.
- **Mejorar las cartas que ya se tienen** al subir de edad, en vez de mazos por
  nivel. Más difícil de entender y de mostrar.
- **Pagar la edad solo con pescado.** Haría que la colocación inicial junto al mar
  decida la partida.

## Preguntas abiertas para Emerson

1. ¿Edades encendidas por defecto en todos los presets, incluida Clásica?
   Propongo que sí, con un interruptor para jugar sin ellas.
2. ¿Tres edades, o cuatro con una "Edad de los Navegantes" reservada para barcos
   y combate más adelante? Propongo tres ahora y dejar la cuarta para cuando haya
   barcos.
3. ¿Las ciudades siguen en la Edad I (como Catan) o pasan a la II? Propongo la I.
4. ¿Llegar a la Edad Dorada da 1 punto, y la meta sigue en 10?
5. ¿Incluimos la Maravilla? ¿Solo en islas grandes?
6. ¿Agregamos un puerto 2:1 de pescado por defecto cuando hay edades?
7. Desarrollos mejorados: ¿te gustan las cartas propuestas? ¿Alguna que quieras
   agregar o quitar?
8. ¿Te gustan los nombres (Colonos, Mar, Dorada)?
9. ¿Las edades de los demás siempre visibles, incluso con niebla? Propongo que sí.
