
import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
import getpass
from tkcalendar import Calendar
import os
import re
import socket
import uuid
import tempfile
import threading

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------------------------------------------------------------
# iu
# ---------------------------------------------------------------
BG            = "#05070D"   # fondo general de la ventana
PANEL         = "#0F1826"   # base de los paneles "vidrio"
PANEL_LIGHT   = "#141F33"   # variante más clara (tabla / editor)
GLOW_CYAN     = "#00F0FF"   # borde brillante cyan
GLOW_CYAN_DIM = "#0C3E44"   # halo tenue cyan (borde exterior)
GLOW_MAG      = "#FF2BD6"   # borde brillante magenta
GLOW_MAG_DIM  = "#3D0F33"   # halo tenue magenta (borde exterior)
TXT           = "#D8FBFF"   # texto principal
TXT_DIM       = "#6E8A99"   # texto secundario
SEL           = "#3A1140"   # fila seleccionada en la tabla

F_HEAD  = ("Segoe UI Semibold", 20)
F_SUB   = ("Segoe UI", 11)
F_BODY  = ("Segoe UI", 12)
F_MONO  = ("Consolas", 11)
F_BTN   = ("Segoe UI Semibold", 12)

# =================================================================
# UBICACIÓN DE LOS DATOS
# =================================================================
# IMPORTANTE — LEER ANTES DE INSTALAR EN VARIOS EQUIPOS:
# Para que las 2-3 PCs vean y agreguen las MISMAS novedades, esta
# ruta tiene que apuntar a una carpeta de RED (compartida), accesible
# desde los 3 equipos con permisos de lectura/escritura. Si cada PC
# usa su carpeta local (APPDATA), cada una va a tener su propia
# base separada y no van a compartir nada.
#
# Reemplazá la línea de abajo por la ruta real de tu carpeta
# compartida, por ejemplo:
#   CARPETA_DATOS = r"\\PC-PRINCIPAL\NovedadesCompartidas"
# o, si mapeaste una unidad de red:
#   CARPETA_DATOS = r"Z:\NovedadesCompartidas"
#
# Mientras no la cambies, cada equipo va a usar su propia carpeta
# local (APPDATA) y NO va a compartir novedades con los otros dos.
# =================================================================
CARPETA_DATOS = os.path.join(
    os.environ["APPDATA"],
    "GestorNovedades"
)

os.makedirs(CARPETA_DATOS, exist_ok=True)

# Carpeta con un .txt por novedad (en vez de un único archivo .db).
# Al ser un archivo por registro, dos personas agregando novedades
# al mismo tiempo desde PCs distintas nunca pisan el mismo archivo:
# cada "Agregar" crea un .txt con nombre único (fecha+hora+PC+azar).
# Esto es justamente lo que evita que el programa se cuelgue o la
# base se corrompa cuando dos operadores escriben a la vez, algo
# que un único archivo .db compartido por red no garantiza.
CARPETA_NOVEDADES = os.path.join(CARPETA_DATOS, "novedades")
os.makedirs(CARPETA_NOVEDADES, exist_ok=True)

DB_LOCK = threading.Lock()

_SEP = "\n===\n"

def _nombre_equipo():
    """Nombre de la PC, saneado para que sirva como parte de un nombre
    de archivo. Se usa para que dos PCs nunca generen el mismo nombre
    aunque agreguen una novedad en el mismo milisegundo exacto."""
    try:
        nombre = socket.gethostname()
    except Exception:
        nombre = "PC"
    return re.sub(r'[^0-9A-Za-z_-]', '_', nombre) or "PC"

def _generar_nombre_archivo():
    """Nombre único para una novedad nueva: timestamp (para que el
    orden alfabético coincida con el orden cronológico) + nombre de
    equipo + sufijo al azar. La combinación hace prácticamente
    imposible que dos PCs generen el mismo nombre, incluso agregando
    novedades en el mismo instante."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
    azar = uuid.uuid4().hex[:6]
    return f"{ts}_{_nombre_equipo()}_{azar}.txt"

def _escribir_archivo_atomico(ruta, contenido):
    """Escribe el contenido en un archivo temporal en la MISMA carpeta
    y recién al final lo renombra al nombre definitivo (os.replace).
    El renombrado es atómico: cualquier otra PC que esté leyendo la
    carpeta en ese instante nunca va a ver un archivo a medio escribir
    ni una novedad corrupta/incompleta, aunque dos personas estén
    guardando al mismo tiempo."""
    carpeta = os.path.dirname(ruta)
    fd, tmp_ruta = tempfile.mkstemp(dir=carpeta, prefix=".tmp_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenido)
        os.replace(tmp_ruta, ruta)
    except Exception:
        if os.path.exists(tmp_ruta):
            os.remove(tmp_ruta)
        raise

def _codificar_novedad(fecha_, usuario_, novedad_):
    return f"FECHA: {fecha_}\nUSUARIO: {usuario_}{_SEP}{novedad_}"

def _decodificar_novedad(contenido):
    if _SEP not in contenido:
        return None
    cabecera, texto = contenido.split(_SEP, 1)
    fecha_ = usuario_ = ""
    for linea in cabecera.splitlines():
        if linea.startswith("FECHA:"):
            fecha_ = linea[len("FECHA:"):].strip()
        elif linea.startswith("USUARIO:"):
            usuario_ = linea[len("USUARIO:"):].strip()
    return fecha_, usuario_, texto.strip()

def guardar_novedad(fecha_, usuario_, novedad_, id_existente=None):
    """Crea una novedad nueva (id_existente=None) o sobreescribe una ya
    existente (Modificar). En ambos casos la escritura es atómica."""
    with DB_LOCK:
        nombre = id_existente or _generar_nombre_archivo()
        ruta = os.path.join(CARPETA_NOVEDADES, nombre)
        _escribir_archivo_atomico(ruta, _codificar_novedad(fecha_, usuario_, novedad_))
        return nombre

def eliminar_novedad(id_):
    ruta = os.path.join(CARPETA_NOVEDADES, id_)
    with DB_LOCK:
        try:
            os.remove(ruta)
        except FileNotFoundError:
            pass

def _leer_registro(nombre_archivo):
    ruta = os.path.join(CARPETA_NOVEDADES, nombre_archivo)
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read()
    except (OSError, UnicodeDecodeError):
        # El archivo pudo haber sido borrado o estar siendo escrito
        # justo en este instante por otra PC (muy improbable gracias
        # al renombrado atómico, pero por las dudas no rompemos la
        # carga de toda la tabla por un solo registro).
        return None
    decodificado = _decodificar_novedad(contenido)
    if decodificado is None:
        return None
    fecha_, usuario_, novedad_ = decodificado
    return {"id": nombre_archivo, "fecha": fecha_, "usuario": usuario_, "novedad": novedad_}

def obtener_todas_las_novedades():
    """Lee y decodifica todas las novedades de la carpeta compartida.
    Se llama siempre desde un hilo de fondo (ver _pedir_carga) para no
    congelar la ventana mientras lee del disco/red."""
    try:
        nombres = [n for n in os.listdir(CARPETA_NOVEDADES) if n.endswith(".txt") and not n.startswith(".tmp_")]
    except FileNotFoundError:
        os.makedirs(CARPETA_NOVEDADES, exist_ok=True)
        return []
    registros = []
    for nombre in nombres:
        r = _leer_registro(nombre)
        if r is not None:
            registros.append(r)
    # El nombre de archivo arranca con el timestamp, así que ordenar
    # por nombre en forma descendente equivale a "más nuevas primero".
    registros.sort(key=lambda r: r["id"], reverse=True)
    return registros

def obtener_id(fecha_txt, usu, nov):
    """Ya no hace falta: el id (nombre de archivo) viaja directamente
    con cada fila de la tabla. Se deja solo por compatibilidad."""
    for r in obtener_todas_las_novedades():
        if r["fecha"] == fecha_txt and r["usuario"] == usu and r["novedad"] == nov:
            return r["id"]
    return None

CARPETA_BACKUP_TXT = os.path.join(CARPETA_DATOS, "backups_diarios")
os.makedirs(CARPETA_BACKUP_TXT, exist_ok=True)

def _nombre_archivo_dia(fecha_str):
    """Convierte 'dd/mm/aaaa' en un nombre de archivo ordenable
    ('aaaa-mm-dd.txt'). Si la fecha viene en un formato raro
    (puede pasar con novedades viejas importadas), cae a un nombre
    saneado en vez de romper."""
    try:
        d = datetime.strptime(fecha_str.strip(), "%d/%m/%Y")
        return d.strftime("%Y-%m-%d") + ".txt"
    except ValueError:
        limpio = re.sub(r'[^0-9A-Za-z_-]', '_', fecha_str.strip()) or "sin_fecha"
        return limpio + ".txt"

def respaldar_dia(fecha_str):
    """Reescribe SOLO el .txt de resumen del día indicado con sus
    novedades actuales (un resumen legible, separado de los .txt
    individuales que son la base de datos real)."""
    if not fecha_str or not fecha_str.strip():
        return
    filas = [
        (r["usuario"], r["novedad"])
        for r in obtener_todas_las_novedades()
        if r["fecha"] == fecha_str
    ]
    ruta = os.path.join(CARPETA_BACKUP_TXT, _nombre_archivo_dia(fecha_str))
    if not filas:
        # Si ya no queda ninguna novedad ese día (se borró la última),
        # no dejamos un archivo vacío dando vueltas.
        if os.path.exists(ruta):
            os.remove(ruta)
        return
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(f"Novedades del {fecha_str}\n")
        f.write("=" * 40 + "\n\n")
        for usuario_, novedad_ in filas:
            f.write(f"Operador: {usuario_}\n")
            f.write("-" * 20 + "\n")
            f.write(novedad_.strip() + "\n\n")

def _generar_backups_iniciales_si_hace_falta():
    """Genera los .txt de resumen por día una sola vez, en segundo
    plano, si la carpeta de backups todavía está vacía."""
    if os.path.isdir(CARPETA_BACKUP_TXT) and os.listdir(CARPETA_BACKUP_TXT):
        return
    def trabajo():
        fechas = {r["fecha"] for r in obtener_todas_las_novedades()}
        for f in fechas:
            respaldar_dia(f)
    threading.Thread(target=trabajo, daemon=True).start()


app=ctk.CTk()
app.geometry("1280x760")
app.title("Gestor de Novedades")
app.configure(fg_color=BG)
# Si tu equipo lo ve demasiado transparente, bajá/subí este valor (0.80-1.0).
app.attributes("-alpha", 0.95)

def _glow_panel(master, glow=GLOW_CYAN, glow_dim=GLOW_CYAN_DIM, fill=PANEL, radius=18):
    """Simula un halo de neón: un marco tenue por fuera + un panel
    'vidrio' con borde brillante por dentro."""
    halo = ctk.CTkFrame(master, fg_color="transparent",
                         border_color=glow_dim, border_width=2,
                         corner_radius=radius+4)
    panel = ctk.CTkFrame(halo, fg_color=fill,
                          border_color=glow, border_width=2,
                          corner_radius=radius)
    panel.pack(fill="both", expand=True, padx=3, pady=3)
    return halo, panel

def _neon_button(master, text, command, glow=GLOW_CYAN, glow_hover=GLOW_MAG):
    btn = ctk.CTkButton(
        master, text=text, command=command, font=F_BTN,
        fg_color="transparent", hover_color=PANEL_LIGHT,
        text_color=TXT, border_color=glow, border_width=2,
        corner_radius=10
    )
    btn.bind("<Enter>", lambda e: btn.configure(border_color=glow_hover, text_color=glow_hover))
    btn.bind("<Leave>", lambda e: btn.configure(border_color=glow, text_color=TXT))
    return btn

header_wrap = ctk.CTkFrame(app, fg_color="transparent")
header_wrap.pack(fill="x", padx=16, pady=(14, 0))

ctk.CTkLabel(header_wrap, text="G E S T O R   D E   N O V E D A D E S",
             font=F_HEAD, text_color=GLOW_CYAN).pack(anchor="w")
ctk.CTkLabel(header_wrap, text="registro operativo diario",
             font=F_SUB, text_color=TXT_DIM).pack(anchor="w", pady=(0, 6))

# Divisor con degradé cyan -> magenta (elemento de firma visual)
divider = ctk.CTkCanvas(app, height=3, bg=BG, highlightthickness=0)
divider.pack(fill="x", padx=16, pady=(0, 10))

def _pintar_divisor(event=None):
    divider.delete("all")
    w = divider.winfo_width()
    if w < 2: return
    c1 = (0x00, 0xF0, 0xFF)
    c2 = (0xFF, 0x2B, 0xD6)
    pasos = max(w // 4, 1)
    for i in range(pasos):
        t = i / pasos
        r = int(c1[0] + (c2[0]-c1[0])*t)
        g = int(c1[1] + (c2[1]-c1[1])*t)
        b = int(c1[2] + (c2[2]-c1[2])*t)
        divider.create_rectangle(i*4, 0, i*4+4, 3, fill=f"#{r:02x}{g:02x}{b:02x}", width=0)

divider.bind("<Configure>", _pintar_divisor)

body = ctk.CTkFrame(app, fg_color="transparent")
body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

left_halo, left = _glow_panel(body, glow=GLOW_CYAN, glow_dim=GLOW_CYAN_DIM)
left_halo.pack(side="left", fill="y", padx=(0, 10))
left_halo.pack_propagate(False)
left_halo.configure(width=280)
left.pack_propagate(True)

right_halo, right = _glow_panel(body, glow=GLOW_MAG, glow_dim=GLOW_MAG_DIM, fill=PANEL_LIGHT)
right_halo.pack(side="right", fill="both", expand=True)

def _entry_neon(master, placeholder):
    e = ctk.CTkEntry(master, placeholder_text=placeholder, font=F_BODY,
                      fg_color=BG, text_color=TXT, placeholder_text_color=TXT_DIM,
                      border_color=GLOW_CYAN_DIM, border_width=1, corner_radius=8)
    e.bind("<FocusIn>", lambda ev: e.configure(border_color=GLOW_CYAN))
    e.bind("<FocusOut>", lambda ev: e.configure(border_color=GLOW_CYAN_DIM))
    return e

fecha=_entry_neon(left,"dd/mm/aaaa")
fecha.pack(fill="x",padx=10,pady=(14,6))
fecha.insert(0, datetime.now().strftime("%d/%m/%Y"))

usuario = _entry_neon(left, "Usuario")
usuario.pack(fill="x", padx=10, pady=6)

usuario.insert(0, getpass.getuser())

buscar_var=ctk.StringVar()
entrada=_entry_neon(left, "Buscar")
entrada.configure(textvariable=buscar_var, border_color=GLOW_MAG_DIM)
entrada.bind("<FocusIn>", lambda ev: entrada.configure(border_color=GLOW_MAG))
entrada.bind("<FocusOut>", lambda ev: entrada.configure(border_color=GLOW_MAG_DIM))
entrada.pack(fill="x",padx=10,pady=6)


style=ttk.Style()
style.theme_use("default")
style.configure("Treeview",
    background=PANEL_LIGHT,
    foreground=TXT,
    fieldbackground=PANEL_LIGHT,
    bordercolor=GLOW_MAG_DIM,
    borderwidth=0,
    rowheight=26,
    font=F_MONO )
style.configure("Treeview.Heading",
    background=PANEL,
    foreground=GLOW_MAG,
    relief="flat",
    font=F_BTN )
style.map("Treeview.Heading", background=[("active", PANEL)])
style.map("Treeview", background=[("selected",SEL)], foreground=[("selected",GLOW_CYAN)])

style.configure("Vertical.TScrollbar",
    background=PANEL, troughcolor=PANEL_LIGHT,
    bordercolor=PANEL_LIGHT, arrowcolor=GLOW_CYAN, relief="flat")
style.map("Vertical.TScrollbar", background=[("active", GLOW_CYAN_DIM)])

# Marco propio para la tabla + su scroll, para que el scroll quede
# pegado al costado derecho de la TABLA (misma altura que ella) en
# vez de flotar suelto en la esquina inferior derecha de todo el
# panel (que es lo que pasaba al empacar la tabla y el scroll por
# separado directamente en "right").
tabla_frame = ctk.CTkFrame(right, fg_color="transparent")
tabla_frame.pack(fill="both", expand=True, padx=10, pady=(10,4))

tabla=ttk.Treeview(
    tabla_frame,
    columns=("Fecha","Operador","Novedad"),
    show="headings"
)

tabla.heading("Fecha", text="Fecha")
tabla.heading("Operador", text="Operador")
tabla.heading("Novedad", text="Novedad")

tabla.column("Fecha", width=85, minwidth=85, stretch=False, anchor="center")
tabla.column("Operador", width=140, minwidth=120, anchor="center")
tabla.column("Novedad", width=800, stretch=True)

scroll = ttk.Scrollbar(tabla_frame,
                       orient="vertical",
                       command=tabla.yview)
tabla.configure(yscrollcommand=scroll.set)

scroll.pack(side="right", fill="y")
tabla.pack(side="left", fill="both", expand=True)

editor=ctk.CTkTextbox(right, fg_color=BG, text_color=TXT, font=F_MONO,
                      border_color=GLOW_MAG_DIM, border_width=1, corner_radius=10,
                      scrollbar_button_color=PANEL, scrollbar_button_hover_color=GLOW_MAG_DIM)
editor.pack(fill="both",expand=True,padx=10,pady=(0,10))
editor.bind("<FocusIn>", lambda ev: editor.configure(border_color=GLOW_MAG))
editor.bind("<FocusOut>", lambda ev: editor.configure(border_color=GLOW_MAG_DIM))

def acerca_de():
    ventana = ctk.CTkToplevel(app)
    ventana.title("Acerca de")
    ventana.geometry("440x260")
    ventana.resizable(False, False)
    ventana.configure(fg_color=BG)
    ventana.attributes("-alpha", 0.96)

    halo, panel = _glow_panel(ventana, glow=GLOW_CYAN, glow_dim=GLOW_CYAN_DIM)
    halo.pack(fill="both", expand=True, padx=12, pady=12)

    ctk.CTkLabel(
        panel,
        text="GESTOR DE NOVEDADES",
        font=F_HEAD,
        text_color=GLOW_CYAN
    ).pack(pady=(24, 4))

    ctk.CTkLabel(
        panel,
        text="Versión 1.9",
        font=F_SUB,
        text_color=TXT_DIM
    ).pack()

    ctk.CTkLabel(
        panel,
        text="Programado por Facundo Pérez\n© 2026",
        font=F_BODY,
        text_color=TXT
    ).pack(pady=(16, 6))

    ctk.CTkLabel(
        panel,
        text="GitHub: TheBlackMarc",
        font=F_BODY,
        text_color=GLOW_MAG
    ).pack()

    ctk.CTkLabel(
        panel,
        text="Marctech",
        font=F_BTN,
        text_color=GLOW_CYAN
    ).pack(pady=(14, 10))

    _neon_button(panel, "Cerrar", ventana.destroy).pack(pady=10, padx=40, fill="x")




def _ventana_progreso(total):
    top = ctk.CTkToplevel(app)
    top.title("Importando...")
    top.geometry("440x190")
    top.resizable(False, False)
    top.configure(fg_color=BG)
    top.attributes("-alpha", 0.97)
    top.protocol("WM_DELETE_WINDOW", lambda: None)  # no se cierra mientras importa
    top.grab_set()

    halo, panel = _glow_panel(top, glow=GLOW_CYAN, glow_dim=GLOW_CYAN_DIM)
    halo.pack(fill="both", expand=True, padx=12, pady=12)

    ctk.CTkLabel(panel, text="IMPORTANDO ARCHIVOS RTF", font=F_BTN,
                 text_color=GLOW_CYAN).pack(pady=(20, 8))

    barra = ctk.CTkProgressBar(panel, progress_color=GLOW_MAG, fg_color=PANEL_LIGHT)
    barra.pack(fill="x", padx=26, pady=8)
    barra.set(0)

    lbl_detalle = ctk.CTkLabel(panel, text=f"0 / {total}", font=F_SUB, text_color=TXT_DIM)
    lbl_detalle.pack(pady=(4, 16))

    def actualizar(idx, total_, importados, duplicados, errores):
        barra.set(idx/total_ if total_ else 0)
        lbl_detalle.configure(
            text=f"{idx}/{total_}   nuevas: {importados}   duplicadas: {duplicados}   errores: {errores}"
        )

    def cerrar():
        top.grab_release()
        top.destroy()

    return top, actualizar, cerrar

_botones_bloqueables = []

def _bloquear_botones(bloquear):
    estado = "disabled" if bloquear else "normal"
    for b in _botones_bloqueables:
        b.configure(state=estado)

def importar_historial_rtf():
    carpeta=filedialog.askdirectory(title="Seleccionar carpeta con archivos antiguos")
    if not carpeta:
        return

    # Junta todas las rutas primero para poder mostrar progreso real
    # (porcentaje) en vez de solo un contador que no dice cuánto falta.
    rutas=[]
    for raiz,_,files in os.walk(carpeta):
        for nombre in files:
            rutas.append(os.path.join(raiz,nombre))

    total=len(rutas)
    if total==0:
        messagebox.showinfo("Importación","No se encontraron archivos en esa carpeta.")
        return

    ventana, actualizar_progreso, cerrar_progreso = _ventana_progreso(total)
    _bloquear_botones(True)

    def trabajo_en_segundo_plano():
        encontrados=importados=duplicados=errores=0
        fechas_tocadas=set()
        # Se arma una sola vez el set de (fecha,novedad) ya existentes,
        # en vez de leer la carpeta entera archivo por archivo en cada
        # iteración del bucle — con miles de .txt eso sería el nuevo
        # cuello de botella.
        existentes = {(r["fecha"], r["novedad"]) for r in obtener_todas_las_novedades()}
        for idx,ruta in enumerate(rutas, start=1):
            nombre=os.path.basename(ruta)
            try:
                data=open(ruta,"rb").read()
                if data.lstrip().startswith(b"{\\rtf"):
                    encontrados+=1
                    raw=data.decode("cp1252","ignore")
                    t=raw.replace("\\par","\n").replace("\\tab","\t")
                    t=re.sub(r'\\[a-zA-Z]+-?\d* ?', '', t)
                    t=re.sub(r"[{}]","",t)
                    t = re.sub(r'^(?:[A-Za-z0-9 _-]+;)+', '', t)
                    t = re.sub(r'^[A-Za-z0-9 _-]+(?:;[A-Za-z0-9 _-]+)+;?$', '', t, flags=re.MULTILINE)
                    t = re.sub(r'\n{2,}', '\n', t)
                    t=re.sub(r"\n{2,}","\n",t).strip()
                    fecha_=""
                    if re.fullmatch(r"\d{8}",nombre):
                        fecha_=f"{nombre[6:8]}/{nombre[4:6]}/{nombre[:4]}"
                    else:
                        fecha_=datetime.now().strftime("%d/%m/%Y")
                    usuario_=""
                    m=re.search(r"TURNO.*?-([^-\n]+(?://[^-\n]+)*)-",t,re.I)
                    if m: usuario_=m.group(1).strip()
                    if (fecha_, t) in existentes:
                        duplicados+=1
                    else:
                        guardar_novedad(fecha_, usuario_, t)
                        existentes.add((fecha_, t))
                        importados+=1
                        fechas_tocadas.add(fecha_)
            except Exception:
                errores+=1

            if idx % 10 == 0 or idx == total:
                app.after(0, actualizar_progreso, idx, total, importados, duplicados, errores)

        # Respalda cada día tocado UNA sola vez (no en cada inserción),
        # para no reescribir el mismo archivo cientos de veces si hay
        # muchas novedades el mismo día.
        for f in fechas_tocadas:
            respaldar_dia(f)

        def finalizar():
            cerrar_progreso()
            _bloquear_botones(False)
            cargar(buscar_var.get())
            messagebox.showinfo(
                "Importación",
                f"RTF detectados: {encontrados}\nImportados: {importados}\nDuplicados: {duplicados}\nErrores: {errores}"
            )
        app.after(0, finalizar)

    threading.Thread(target=trabajo_en_segundo_plano, daemon=True).start()

LIMIT_TABLA = 5  # filas que se muestran de una por defecto (sin búsqueda); ver nota abajo

_tabla_generacion = 0

def _pedir_carga(filtro="", fecha_exacta=None):
    """Lee la carpeta de novedades en un hilo aparte (puede ser una
    carpeta de red, y listar/leer miles de archivos ahí no es
    instantáneo) y vuelca el resultado en la tabla desde el hilo
    principal. El número de 'generación' evita que una consulta vieja
    (por ejemplo de una búsqueda ya superada) pise en pantalla el
    resultado de una más nueva que terminó antes."""
    global _tabla_generacion
    _tabla_generacion += 1
    mi_generacion = _tabla_generacion

    def trabajo():
        registros = obtener_todas_las_novedades()
        if fecha_exacta is not None:
            registros = [r for r in registros if r["fecha"] == fecha_exacta]
        elif filtro:
            f = filtro.lower()
            registros = [
                r for r in registros
                if f in r["fecha"].lower() or f in r["usuario"].lower() or f in r["novedad"].lower()
            ]
        else:
            # Sin búsqueda y sin fecha puntual: solo se listan las
            # LIMIT_TABLA más recientes, para no insertar miles de filas
            # en la tabla visual apenas se abre el programa. Con una
            # búsqueda (o un día del calendario) SIEMPRE se muestran
            # TODAS las coincidencias, sin este límite.
            registros = registros[:LIMIT_TABLA]
        app.after(0, lambda: _aplicar_resultados(registros, mi_generacion))

    threading.Thread(target=trabajo, daemon=True).start()

def _aplicar_resultados(registros, mi_generacion):
    if mi_generacion != _tabla_generacion:
        return
    for i in tabla.get_children():
        tabla.delete(i)
    for r in registros:
        # El nombre de archivo (id) viaja como iid de la fila: así
        # Modificar/Eliminar saben exactamente qué archivo tocar, sin
        # tener que volver a buscarlo por contenido.
        tabla.insert("", "end", iid=r["id"], values=(r["fecha"], r["usuario"], r["novedad"]))

def cargar(filtro=""):
    _pedir_carga(filtro=filtro)


def cargar_por_fecha(fecha_seleccionada):
    _pedir_carga(fecha_exacta=fecha_seleccionada)


ultimo_formulario = {"fecha":"","usuario":"","novedad":""}

def limpiar_formulario():
    global ultimo_formulario
    ultimo_formulario={
        "fecha":fecha.get(),
        "usuario":usuario.get(),
        "novedad":editor.get("1.0","end")
    }
    fecha.delete(0,"end")
    fecha.insert(0, datetime.now().strftime("%d/%m/%Y"))
    usuario.delete(0,"end")
    usuario.insert(0,getpass.getuser())
    editor.delete("1.0","end")

def deshacer_limpiar():
    fecha.delete(0,"end")
    fecha.insert(0,ultimo_formulario["fecha"])
    usuario.delete(0,"end")
    usuario.insert(0,ultimo_formulario["usuario"])
    editor.delete("1.0","end")
    editor.insert("1.0",ultimo_formulario["novedad"])

def agregar():
    if not fecha.get().strip() or not editor.get("1.0","end").strip():
        return messagebox.showerror("Error","Complete fecha y novedad")
    fecha_=fecha.get().strip()
    guardar_novedad(fecha_, usuario.get().strip(), editor.get("1.0","end").strip())
    respaldar_dia(fecha_)
    editor.delete("1.0","end")
    limpiar_formulario()
    cargar(buscar_var.get())

_busqueda_after_id = None

def _programar_busqueda(*_):
    """Se llama en cada tecla. En vez de buscar al toque, espera 250ms
    de pausa antes de disparar la consulta — así no se acumula una
    búsqueda por cada letra tipeada."""
    global _busqueda_after_id
    if _busqueda_after_id is not None:
        app.after_cancel(_busqueda_after_id)
    _busqueda_after_id = app.after(250, lambda: cargar(buscar_var.get()))

def seleccionar(e=None):#z
    s=tabla.selection()
    if not s: return
    f,u,n=tabla.item(s[0])["values"]
    fecha.delete(0,"end"); fecha.insert(0,f)
    usuario.delete(0,"end"); usuario.insert(0,u)
    editor.delete("1.0","end"); editor.insert("1.0",n); resaltar_busqueda()

def _id_seleccionado():
    """El nombre de archivo de la novedad seleccionada viaja como iid
    de la fila (ver _aplicar_resultados), así Modificar/Eliminar actúan
    siempre sobre el archivo correcto sin tener que volver a buscarlo
    por contenido."""
    s = tabla.selection()
    return s[0] if s else None

def resaltar_busqueda():
    editor.tag_remove("buscar", "1.0", "end")

    palabra = buscar_var.get().strip()

    if not palabra:
        return

    inicio = "1.0"

    while True:
        pos = editor.search(
            palabra,
            inicio,
            stopindex="end",
            nocase=True
        )

        if not pos:
            break

        fin = f"{pos}+{len(palabra)}c"

        editor.tag_add("buscar", pos, fin)

        inicio = fin

    editor.tag_config(
        "buscar",
        background="light green",
        foreground="black"
    )

def modificar():
    s=tabla.selection()
    if not s:return
    f,u,n=tabla.item(s[0])["values"]
    id_=_id_seleccionado()
    if not id_: return
    fecha_nueva=fecha.get().strip()
    guardar_novedad(fecha_nueva, usuario.get().strip(), editor.get("1.0","end").strip(), id_existente=id_)
    respaldar_dia(f)             # día original (por si la novedad se movió de fecha)
    if fecha_nueva != f:
        respaldar_dia(fecha_nueva)
    cargar(buscar_var.get())

def eliminar():
    s=tabla.selection()
    if not s:return
    f,u,n=tabla.item(s[0])["values"]
    id_=_id_seleccionado()
    if not id_: return
    eliminar_novedad(id_)
    respaldar_dia(f)
    editor.delete("1.0","end")
    limpiar_formulario()
    cargar(buscar_var.get())

buscar_var.trace_add("write",_programar_busqueda)

btn_agregar=_neon_button(left,"Agregar",agregar)
btn_agregar.pack(fill="x",padx=10,pady=4)
btn_modificar=_neon_button(left,"Modificar",modificar)
btn_modificar.pack(fill="x",padx=10,pady=4)
btn_eliminar=_neon_button(left,"Eliminar",eliminar,glow=GLOW_MAG,glow_hover=GLOW_CYAN)
btn_eliminar.pack(fill="x",padx=10,pady=4)
btn_importar=_neon_button(left,"Importar historial RTF",importar_historial_rtf,glow=GLOW_CYAN_DIM,glow_hover=GLOW_MAG)
btn_importar.pack(fill="x",padx=10,pady=4)
_neon_button(left,"Limpiar",limpiar_formulario).pack(fill="x",padx=10,pady=4)
_neon_button(left,"Retroceso",deshacer_limpiar).pack(fill="x",padx=10,pady=4)

_botones_bloqueables.extend([btn_agregar, btn_modificar, btn_eliminar, btn_importar])

cal = Calendar(
    left,
    selectmode="day",
    date_pattern="dd/mm/yyyy",
    background=PANEL,
    foreground=GLOW_CYAN,
    disabledbackground=PANEL,
    disabledforeground=TXT_DIM,
    bordercolor=GLOW_CYAN_DIM,
    headersbackground=PANEL,
    headersforeground=GLOW_MAG,
    normalbackground=PANEL_LIGHT,
    normalforeground=TXT,
    weekendbackground="#1A0F26",
    weekendforeground=TXT,
    selectbackground=GLOW_MAG,
    selectforeground=BG,
    othermonthbackground=PANEL,
    othermonthwebackground=PANEL,
    othermonthforeground=TXT_DIM,
    othermonthweforeground=TXT_DIM,
    tooltipbackground=PANEL,
    font=F_SUB,
    locale="es_ES"
)

cal.pack(fill="both", expand=False, padx=10, pady=10)

fecha_filtrada=None

def mostrar_todas():
    global fecha_filtrada
    fecha_filtrada=None
    cargar(buscar_var.get())

def actualizar_fecha(event=None):
    global fecha_filtrada
    fecha_seleccionada=cal.get_date()
    if fecha_filtrada==fecha_seleccionada:
        fecha_filtrada=None
        fecha.delete(0,"end")
        fecha.insert(0, datetime.now().strftime("%d/%m/%Y"))
        cargar(buscar_var.get())
        return
    fecha_filtrada=fecha_seleccionada
    fecha.delete(0,"end")
    fecha.insert(0,fecha_seleccionada)
    cargar_por_fecha(fecha_seleccionada)

cal.bind("<<CalendarSelected>>", actualizar_fecha)

_neon_button(left,"Mostrar todas",mostrar_todas).pack(fill="x",padx=10,pady=4)

_neon_button(left,"Acerca de",acerca_de,glow=GLOW_CYAN_DIM,glow_hover=GLOW_MAG).pack(fill="x", padx=10, pady=(4,12))

tabla.bind("<<TreeviewSelect>>",seleccionar)
_generar_backups_iniciales_si_hace_falta()
cargar()
app.mainloop()
