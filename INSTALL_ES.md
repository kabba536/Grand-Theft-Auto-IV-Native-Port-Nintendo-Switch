# Guía de instalación en español

GTA4NX ejecuta Grand Theft Auto IV de Xbox 360 de forma nativa en Nintendo Switch mediante
recompilación estática. **No se incluyen archivos del juego:** necesitas tu propia copia de GTA IV
para Xbox 360 (región USA) y la actualización Title Update 8.

> [!IMPORTANT]
> **La versión final todavía está en desarrollo.** Estas dos compilaciones son opciones de prueba
> claramente separadas mientras continúa el trabajo para conseguir un port verdaderamente digno
> de Nintendo Switch.

## 1. Elige una versión

No mezcles el archivo `gta4nx.nro` de una versión con el `native.toml` de la otra.

### v35 — Performance Edition

- Estado: compilación de prueba estable.
- Recomendada para empezar y para quien prioriza un comportamiento más conocido.
- Usa una distancia de detalle cercana de 0,45, horizonte de 150 m y más tráfico y peatones.
- Descarga: [v35-performance](https://github.com/kabba536/Grand-Theft-Auto-IV-Native-Port-Nintendo-Switch/releases/tag/v35-performance).

### v50 RC1 — Quality Edition

- Estado: **candidata / pre-release**, no es la versión final.
- Recomendada para probar las optimizaciones más recientes y mayor detalle geométrico cercano.
- Usa detalle cercano de 0,65, horizonte de 100 m y menos población para compensar el coste.
- Conserva completas las sombras de vehículos, personas, ruedas, pelo y armas.
- Todavía necesita más pruebas reales en consola, especialmente en sesiones largas.
- Descarga: [v50-quality-rc1](https://github.com/kabba536/Grand-Theft-Auto-IV-Native-Port-Nintendo-Switch/releases/tag/v50-quality-rc1).

## 2. Requisitos

- Nintendo Switch con custom firmware **Atmosphère**.
- Imagen de tu propio disco de **GTA IV para Xbox 360, región USA**.
- **Title Update 8**, normalmente con un nombre que empieza por `TU_1A581VI_`.
- Aproximadamente 10 GB libres en la tarjeta SD.
- Se recomienda jugar en modo dock por la mayor frecuencia de la GPU.

## 3. Copia GTA4NX a la tarjeta SD

1. Abre la página de la versión elegida.
2. Descarga el ZIP cuyo nombre termina en `performance.zip` o `quality-rc1.zip`. El ZIP que contiene
   `source-code` es solamente para desarrolladores.
3. Extrae el ZIP directamente en la raíz de la tarjeta SD.
4. Comprueba que existen exactamente estas rutas:

   ```text
   sdmc:/switch/gta4nx/gta4nx.nro
   sdmc:/switch/gta4nx/LibertyRecomp/native.toml
   ```

Si después de extraer aparece una carpeta adicional como
`GTA4NX-v35-performance/switch/...`, mueve la carpeta `switch` a la raíz de la SD.

## 4. Copia tus propios archivos de GTA IV

1. Extrae el contenido de tu propia imagen de disco.
2. Copia el contenido del disco dentro de:

   ```text
   sdmc:/switch/gta4nx/install/gta4_disc/
   ```

3. Copia la carpeta de Title Update 8 dentro de `install`, conservando su nombre:

   ```text
   sdmc:/switch/gta4nx/install/TU_1A581VI_.../
   ```

El proyecto no proporciona ni enlaza estos archivos con copyright.

## 5. Primer inicio

1. En el menú HOME, selecciona cualquier juego instalado.
2. **Mantén pulsado R** mientras abres el juego para entrar en Homebrew Menu en modo título y
   disponer de toda la memoria.
3. No abras GTA4NX desde el Álbum: ese modo no proporciona suficiente memoria.
4. En Homebrew Menu, selecciona GTA IV.
5. El primer inicio instala los datos y crea la caché de shaders. Puede tardar y producir muchos
   tirones durante los primeros minutos. Es normal.

## 6. Actualizar o cambiar de versión

1. Cierra GTA4NX por completo.
2. Descarga el ZIP de la nueva versión.
3. Sustituye **juntos** estos dos archivos:

   ```text
   switch/gta4nx/gta4nx.nro
   switch/gta4nx/LibertyRecomp/native.toml
   ```

4. No mezcles archivos de v35 y v50.
5. No borres la carpeta `install`, porque contiene los archivos que copiaste desde tu propio juego.
6. Después de cambiar de versión pueden aparecer tirones mientras se vuelve a preparar la caché de
   shaders.

## 7. Problemas frecuentes

### Error al iniciar desde un icono forwarder

Inicia un juego instalado manteniendo R y abre GTA4NX desde Homebrew Menu en modo título. El
forwarder del menú HOME no funciona correctamente por ahora.

### El juego se cierra por falta de memoria

Usa el `native.toml` incluido sin aumentar `gta4_streaming_budget_scale` por encima de 1.25. Valores
superiores no han mejorado el rendimiento y sí han provocado errores de memoria en pruebas previas.

### Rendimiento bajo en modo portátil

El modo portátil utiliza una frecuencia de GPU inferior. Prueba el modo dock antes de informar de
una regresión de rendimiento.

### Tirones durante los primeros minutos

La caché de shaders todavía se está creando. Juega unos minutos y vuelve a visitar la misma zona
antes de comparar el rendimiento.

### Sombras incorrectas en v50 RC1

La v50 contiene la corrección de estado que faltaba en v49, pero continúa siendo candidata. Si ves
sombras que parpadean o desaparecen, prueba v35 para comparar y envía los registros indicados abajo.

## 8. Cómo informar de un problema

Abre una incidencia en GitHub e indica:

- la versión exacta: `v35-performance` o `v50-quality-rc1`;
- el lugar, misión y situación en la que apareció el problema;
- si hubo cierre, congelación, sombras rotas o solamente pérdida de rendimiento;
- cuánto tiempo llevaba abierta la sesión;
- la carpeta `sdmc:/switch/gta4nx/logs/`, comprimida en ZIP.

No subas la imagen del disco, la actualización ni otros archivos del juego.
