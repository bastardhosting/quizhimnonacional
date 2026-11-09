import json
import os
import random
import re
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify

app = Flask(__name__)
app.secret_key = 'clave-secreta-quiz-himno-honduras-100'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MUSICA_DIR = os.path.join(BASE_DIR, 'static', 'musica')
PREGUNTAS_FILE = os.path.join(BASE_DIR, 'preguntas')
SESSION_DIR = os.path.join(BASE_DIR, 'sessions')
os.makedirs(SESSION_DIR, exist_ok=True)

def obtener_musica():
    if not os.path.exists(MUSICA_DIR):
        return []
    archivos = []
    for f in os.listdir(MUSICA_DIR):
        if f.lower().endswith(('.mp3', '.wav', '.ogg', '.m4a')):
            archivos.append(f)
    return sorted(archivos)

MUSICA_LISTA = obtener_musica()

def _estado_path(qid):
    return os.path.join(SESSION_DIR, f'{qid}.json')

def cargar_estado(qid):
    path = _estado_path(qid)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'current': 0, 'score': 0, 'answers': []}

def guardar_estado(qid, estado):
    path = _estado_path(qid)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False)

def limpiar_estado(qid):
    path = _estado_path(qid)
    if os.path.exists(path):
        os.remove(path)

def reparar_mojibake(texto):
    try:
        return texto.encode('latin-1').decode('utf-8')
    except Exception:
        return texto

def parse_preguntas(path):
    with open(path, 'r', encoding='latin-1') as f:
        texto = f.read()
    texto = reparar_mojibake(texto)

    marcadores = []
    for m in re.finditer(r'(?<!\d)(\d{1,3})\.\s', texto):
        n = int(m.group(1))
        if 1 <= n <= 100:
            marcadores.append((m.start(), m.end(), n))
    marcadores.sort(key=lambda x: x[0])

    preguntas = []
    basura = [
        'Cuestionario Civico del Himno Nacional Acento Metrico',
        'Cuestionario Civico del Himno Nacional Doblar la Bandera',
        'Cuestionario Civico del Himno Nacional Posicion de las estrellas',
        'Ver más',
        'Mapas de Honduras',
        'Consultar atlas',
        'Escuchar Música',
        'B. De la explicación del Himno Nacional en forma breve',
        'C. De la Bandera, su Historia, usos y otros datos',
        'D. Gráfica ilustrativa para doblar nuestra Bandera Nacional',
        'E. Figura ilustrativa para confeccionar nuestra Bandera Nacional',
        'F. Del Escudo, su significado e interpretación de sus atributos',
    ]

    for i, (start, end, n) in enumerate(marcadores):
        seg_end = marcadores[i + 1][0] if i + 1 < len(marcadores) else len(texto)
        segmento = texto[end:seg_end]

        if 'R=' in segmento:
            idx = segmento.index('R=')
            pregunta_texto = segmento[:idx].strip()
            respuesta = segmento[idx + 2:].strip()
        else:
            pregunta_texto = segmento.strip()
            respuesta = ''

        for b in basura:
            pregunta_texto = pregunta_texto.replace(b, '')
            respuesta = respuesta.replace(b, '')

        pregunta_texto = re.sub(r'\s+', ' ', pregunta_texto).strip()
        respuesta = re.sub(r'\s+', ' ', respuesta).strip()

        if pregunta_texto:
            preguntas.append({
                'id': n,
                'pregunta': pregunta_texto,
                'respuesta': respuesta,
            })

    return preguntas

RAW_PREGUNTAS = parse_preguntas(PREGUNTAS_FILE)

def construir_quiz():
    respuestas = [p['respuesta'] for p in RAW_PREGUNTAS if p['respuesta']]
    quiz = []
    for p in RAW_PREGUNTAS:
        correcta = p['respuesta']
        distractores = [r for r in respuestas if r != correcta]
        random.shuffle(distractores)
        opciones = [correcta] + distractores[:3]
        random.shuffle(opciones)
        correct_idx = opciones.index(correcta)
        opciones = [o[:120] + ('...' if len(o) > 120 else '') for o in opciones]
        quiz.append({
            'id': p['id'],
            'pregunta': p['pregunta'],
            'opciones': opciones,
            'respuesta_correcta': correct_idx,
            'explicacion': correcta if correcta else '',
        })
    return quiz

QUIZ_DATA = construir_quiz()

@app.route('/musica/<path:filename>')
def servir_musica(filename):
    return send_from_directory(MUSICA_DIR, filename)

@app.route('/')
def index():
    return render_template('index.html', total=len(QUIZ_DATA), musica=MUSICA_LISTA)

@app.route('/quiz')
def quiz():
    qid = str(uuid.uuid4())
    guardar_estado(qid, {'current': 0, 'score': 0, 'answers': []})
    return redirect(url_for('quiz_play', qid=qid))

@app.route('/quiz/play')
def quiz_play():
    qid = request.args.get('qid') or str(uuid.uuid4())
    return render_template('quiz_play.html', total=len(QUIZ_DATA), musica=MUSICA_LISTA, qid=qid)

@app.route('/api/question', methods=['GET', 'POST'])
def api_question():
    qid = request.args.get('qid')
    estado = cargar_estado(qid)
    current = estado.get('current', 0)

    if request.method == 'POST':
        user_answer = request.args.get('respuesta', '').strip()
        if not user_answer:
            user_answer = '-1'
        if current >= len(QUIZ_DATA):
            answers = estado.get('answers', [])
            score = estado.get('score', 0)
            total = len(QUIZ_DATA)
            porcentaje = round((score / total) * 100) if total > 0 else 0
            return jsonify({'step': 'resultados', 'resultados': answers,
                            'puntuacion': score, 'total': total, 'porcentaje': porcentaje})

        pregunta = QUIZ_DATA[current]
        correct_idx = pregunta['respuesta_correcta']
        opcion_correcta = pregunta['opciones'][correct_idx]

        es_correcta = user_answer != '' and int(user_answer) == correct_idx

        if es_correcta:
            estado['score'] = estado.get('score', 0) + 1

        estado['answers'].append({
            'id': pregunta['id'],
            'pregunta': pregunta['pregunta'],
            'respuesta_usuario': pregunta['opciones'][int(user_answer)] if user_answer != '' and int(user_answer) >= 0 else 'No respondida',
            'respuesta_correcta': opcion_correcta,
            'es_correcta': es_correcta,
            'explicacion': pregunta['explicacion']
        })

        estado['current'] = current + 1
        guardar_estado(qid, estado)

        next_current = estado['current']
        if next_current >= len(QUIZ_DATA):
            answers = estado.get('answers', [])
            score = estado.get('score', 0)
            total = len(QUIZ_DATA)
            porcentaje = round((score / total) * 100) if total > 0 else 0
            return jsonify({
                'step': 'resultados',
                'resultados': answers,
                'puntuacion': score,
                'total': total,
                'porcentaje': porcentaje,
            })

        return jsonify({
            'step': 'feedback',
            'resultado': estado['answers'][-1],
            'numero': estado['answers'][-1]['id'],
            'total': len(QUIZ_DATA),
            'score': estado.get('score', 0),
            'current': next_current,
        })

    if current >= len(QUIZ_DATA):
        answers = estado.get('answers', [])
        score = estado.get('score', 0)
        total = len(QUIZ_DATA)
        porcentaje = round((score / total) * 100) if total > 0 else 0
        return jsonify({'step': 'resultados', 'resultados': answers,
                        'puntuacion': score, 'total': total, 'porcentaje': porcentaje})

    pregunta = QUIZ_DATA[current]
    progreso = round(((current) / len(QUIZ_DATA)) * 100)
    return jsonify({
        'step': 'question',
        'pregunta': pregunta,
        'numero': current + 1,
        'total': len(QUIZ_DATA),
        'progreso': progreso,
    })

@app.route('/api/saltar-final', methods=['POST'])
def api_saltar_final():
    qid = request.args.get('qid')
    estado = cargar_estado(qid)
    total = len(QUIZ_DATA)
    estado['current'] = total - 1  # índice de la última pregunta
    guardar_estado(qid, estado)
    pregunta = QUIZ_DATA[total - 1]
    progreso = round(((total - 1) / total) * 100)
    return jsonify({
        'step': 'question',
        'pregunta': pregunta,
        'numero': total,
        'total': total,
        'progreso': progreso,
    })

@app.route('/api/resultados')
def api_resultados():
    qid = request.args.get('qid')
    estado = cargar_estado(qid)
    answers = estado.get('answers', [])
    score = estado.get('score', 0)
    total = len(QUIZ_DATA)
    porcentaje = round((score / total) * 100) if total > 0 else 0
    return jsonify({
        'step': 'resultados',
        'resultados': answers,
        'puntuacion': score,
        'total': total,
        'porcentaje': porcentaje,
    })

@app.route('/feedback')
def feedback():
    return redirect(url_for('quiz_play'))

@app.route('/question')
def question():
    return redirect(url_for('quiz_play'))

@app.route('/resultados')
def resultados():
    return redirect(url_for('quiz_play'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
