import asyncio
import os

from spade import agent
import controller as ctrl

from chatterbot import ChatBot
from chatterbot.trainers import ListTrainer

from spade import quit_spade
from spade.agent import Agent
from spade.message import Message
from spade.template import Template
from spade.behaviour import OneShotBehaviour, State
from spade.behaviour import FSMBehaviour
from spade.behaviour import CyclicBehaviour

import csv
import pickle
import pandas as pd
from os import walk
from os import remove
from os.path import join
from os.path import exists
from os.path import basename
from matplotlib import pyplot as plt

from nltk import pos_tag
from nltk.corpus import wordnet as wn
from nltk.corpus import stopwords as sw
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

from sklearn.svm import SVC
from sklearn import model_selection
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import plot_confusion_matrix
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer

#******************************************************************************************************************************************
#******************************************************************************************************************************************
#******************************************************************************************************************************************
#******************************************************************************************************************************************

class ChatBotAgent(Agent):

    __textFromGui = None

    def __init__(self, *args, **kwargs):

        # Llamada a la super (Agent).
        super().__init__(*args, **kwargs)

        # Texto a responder para clasificar.
        self.answerForClassification = "give me the new"

        # Texto a mostrar por defecto cuando no se entiende la entrada del usuario.
        self.defaultAnswer = "I'm sorry, but I don't understand."

    @staticmethod
    def setUserText(text):
        ChatBotAgent.__textFromGui = text
        
    @staticmethod
    def getUserText():
        return ChatBotAgent.__textFromGui

    # Esta clase interna sirve para definir el comportamiento del agente.
    class fsmBehaviour(FSMBehaviour):
        
        def __init__(self, *args, **kwargs):
            
            # Llamada a la super (Agent).
            super().__init__(*args, **kwargs)

    class initState(State):

        # Este método se llama después de ejecutarse on_start().
        async def run(self):

            # Comprobamos que existen ambos ficheros, de lo contrario hay que realizar el entrenamiento.
            if not (exists("database.sqlite3") and exists("sentence_tokenizer.pickle")):

                # Si queda alguno de ellos hay que eliminarlos para volver a generarlos.
                if exists("database.sqlite3"): remove("database.sqlite3")
                if exists("sentence_tokenizer.pickle"): remove("sentence_tokenizer.pickle")

                # Instanciamos un chatBot.
                self.agent.chatBot = ChatBot(
                    name='ChatBot',
                    read_only=True,
                    storage_adapter='chatterbot.storage.SQLStorageAdapter',
                    logic_adapters=[
                        {
                            'import_path': 'chatterbot.logic.BestMatch',
                            'maximum_similarity_threshold': 0.80,
                            'default_response': self.agent.defaultAnswer
                        }
                    ],
                    database_uri='sqlite:///database.sqlite3'
                )

                # Grafos de las conversaciones.
                dialogs = (
                    ['classify', self.agent.answerForClassification],
                    ['classify new', self.agent.answerForClassification],
                    ['classify this', self.agent.answerForClassification],
                    ['i want you to classify this new', self.agent.answerForClassification]
                )

                # Objeto para entrenar al bot con las conversaciones definidas.
                trainer = ListTrainer(self.agent.chatBot)

                # Entrenamos al bot con las conversaciones definidas.
                for dialog in dialogs:
                    trainer.train(dialog)

            # Cambiamos al estado INPUT en que averiguamos que quiere el usuario.
            self.set_next_state("INPUT_STATE")

    class inputState(State):

        # Este método se llama después de ejecutarse on_start().
        async def run(self):
            
            # Mientras no se detecte una entrada del usuario.
            while ChatBotAgent.getUserText() is None:
                pass

            # Recogemos la respuesta del chatBot.
            text = str(self.agent.chatBot.get_response(ChatBotAgent.getUserText()))

            # Devolvemos el texto para que llegue a la GUI.
            ctrl.Controller.getInstance().action({'event': 'BOT_ANSWER', 'object': "bot > " + text})

            # Volvemos a dejar el texto en None para que vuelva a quedarse esperando en el bucle.
            ChatBotAgent.setUserText(None)

            # Pasamos a clasificar o ciclamos en el estado.
            if text == self.agent.answerForClassification:
                self.set_next_state("NEWS_STATE")
            else:
                self.set_next_state("INPUT_STATE")

    class newsState(State):

        # Este método se llama después de ejecutarse on_start().
        async def run(self):

            # Mientras no se detecte una entrada del usuario.
            while ChatBotAgent.getUserText() is None:
                pass

            # Envía el mensaje.
            await self.send(msg=Message(to="dasi2@blabber.im", body=ChatBotAgent.getUserText()))

            # Si no se introduce un poco de retardo, el envío podría no completarse.
            await asyncio.sleep(0.2)

            # Volvemos a dejar el texto en None para que vuelva a quedarse esperando en el bucle.
            ChatBotAgent.setUserText(None)

            # Volvemos al estado inicial para saber que quiere el usuario.
            self.set_next_state("INPUT_STATE")

    # Este método se llama cuando se inicializa el agente.
    async def setup(self):
        
        # Declaramos el comportamiento compuesto.
        fsm = self.fsmBehaviour()
        
        # Declaramos los subcomportamientos.
        fsm.add_state(name="INIT_STATE", state=self.initState(), initial=True)
        fsm.add_state(name="INPUT_STATE", state=self.inputState())
        fsm.add_state(name="NEWS_STATE", state=self.newsState())

        # Declaramos las posibles transiciones entre estados.
        fsm.add_transition(source="INIT_STATE", dest="INPUT_STATE")
        fsm.add_transition(source="INPUT_STATE", dest="INPUT_STATE")
        fsm.add_transition(source="INPUT_STATE", dest="NEWS_STATE")
        fsm.add_transition(source="NEWS_STATE", dest="INPUT_STATE")

        # Encolamos el siguiente comportamiento.
        self.add_behaviour(behaviour=fsm)

#******************************************************************************************************************************************
#******************************************************************************************************************************************
#******************************************************************************************************************************************
#******************************************************************************************************************************************



def preprocessing(textLine):
    
    '''
    # Lemmatization: 
    # Tokenization: Dividimos una frase en palabras.
    # pos_tag devuele pares (<word>, <typeOfWord>), donde <typeOfWord> puede ser un nombre, un verbo un adjetivo, un advervio, etc ...
    # Solo aceptaremos palabras puramente alfabéticas y que no sean stopwords, es decir, palabras que no tienen un significado por sí solas,
    # suelen ser: artículos, pronombres, preposiciones y adverbios. Los buscadores obvian estas palabras.
    '''

    lemmatizedTextLine = ""
    lemmatizer = WordNetLemmatizer()
    
    for word, tag in pos_tag(word_tokenize(textLine.lower())):
        if word not in sw.words('english') and word.isalpha():
            lemmatizedTextLine += lemmatizer.lemmatize(word) + " "
        
    return lemmatizedTextLine.rstrip()



class ClassifierAgent(Agent):

    def __init__(self, *args, **kwargs):
        
        # Llamada a la super (Agent).
        super().__init__(*args, **kwargs)

    # Esta clase interna sirve para definir el comportamiento del agente.
    class InitBehaviour(OneShotBehaviour):

        # Este método se llama después de ejecutarse on_start().
        async def run(self):

            # Crearemos un corpus, es decir, un conjunto de textos de diversas clases ordenados y clasificados. 
            corpus = None

            # Comprobamos que exista el fichero con las noticias clsificadas.
            if not exists('newsClassified.csv'):

                # Creamos el fichero que contendrá las noticias clasificadas.
                with open('newsClassified.csv', 'w') as csvFile:

                    # Escribimos una primera fila a modo de cabecera.
                    csvWriter = csv.writer(csvFile)
                    csvWriter.writerow(["new", "label"])

                    # Obtenemos las listas de los ficheros de cada directorio.
                    for directory, _, files in walk('bbcsport'):

                        # Recorremos la lista de ficheros del directorio actual.
                        for f in files:

                            # Abrimos el fichero que corresponda del directorio actual.
                            with open(join(directory, f), 'r', encoding='latin-1') as file:

                                # Escribimos dos columnas: contenido de la noticia y tipo de deporte.
                                csvWriter.writerow([file.read(), basename(directory)])


                # Creamos un corpus, es decir, un conjunto de textos de diversas clases ordenados y clasificados. 
                corpus = pd.read_csv("newsClassified.csv", encoding='utf-8')

                # Preprocesamos los textos de cada noticia.
                corpus['lemmatizedNew'] = corpus['new'].map(preprocessing)

            # Comprobamos que existan los ficheros relacionados con el clasificador, si no, los generamos.
            if not (exists("svm.pkl") and exists("labelEncoder.pkl") and exists("tFidfMatrixVector.pkl")):

                # Si queda alguno de ellos hay que eliminarlos para volver a generarlos.
                if exists("svm.pkl"): remove("svm.pkl")
                if exists("labelEncoder.pkl"): remove("labelEncoder.pkl")
                if exists("tFidfMatrixVector.pkl"): remove("tFidfMatrixVector.pkl")

                # Otenemos para el texto de cada noticia su vector TF-IDF.
                tfIdfMatrixVectors = TfidfVectorizer()
                texts = tfIdfMatrixVectors.fit_transform(corpus['lemmatizedNew'])

                # LabelEncoder convierte las etiquetas de las clases en identificadores numéricos que van de 0 a N-Clases.
                labelEncoder = LabelEncoder()
                labels = labelEncoder.fit_transform(corpus['label'])

                # Dividimos los datos en un set de entrenamiento y en un set de pruebas.
                trainValues, testValues, trainResults, testResults = train_test_split(texts, labels, test_size=0.25)

                # Clasificador SVM.
                svm = SVC(C=1, kernel='linear', degree=3, gamma='auto')

                # Ajusta el clasificador al modelo de datos.
                svm.fit(trainValues, trainResults)

                # Serializamos los objetos.
                pickle.dump(svm, open('svm.pkl', 'wb'))
                pickle.dump(labelEncoder, open('labelEncoder.pkl', 'wb'))
                pickle.dump(tfIdfMatrixVectors, open('tFidfMatrixVector.pkl', 'wb'))

            else:

                pass

    # Esta clase interna sirve para definir el comportamiento del agente.
    class WaitForRequest(CyclicBehaviour):

        # Este método se llama después de ejecutarse on_start().
        async def run(self):

            # Espera como mucho N segundos para recibir algún mensaje.
            newsName = await self.receive(timeout=3600)
            
            # msg es un objeto o bien Message o bien None. 
            if newsName:
                
                # Cargar la máquina de vectores de soporte.
                svm = pickle.load(open('svm.pkl', 'rb'))

                # Cargamos el conversor de etiquetas.
                labelEncoder = pickle.load(open('labelEncoder.pkl', 'rb'))

                # Cargamos la matriz de vectores TF-IDF.
                tFidfMatrixVector = pickle.load(open('tFidfMatrixVector.pkl', 'rb'))

                # Vamos a clasificar un nuevo texto ajeno a los textos para el entrenamiento y el testing.
                tfIdfVectorOfNewText = tFidfMatrixVector.transform([preprocessing(newsName.body)])

                # Realizamos la predicción.
                svmPrediction = svm.predict(tfIdfVectorOfNewText)

                # Mostramos el resultado.
                print("La noticia pertenece a la clase: ", labelEncoder.inverse_transform(svmPrediction)[0])

    # Este método se llama cuando se inicializa el agente.
    async def setup(self):

        # Encolamos el siguiente comportamiento.
        self.add_behaviour(behaviour=self.InitBehaviour())

        # Encolamos el siguiente comportamiento.
        self.add_behaviour(behaviour=self.WaitForRequest(), template=Template(to="dasi2@blabber.im"))

#******************************************************************************************************************************************
#******************************************************************************************************************************************
#******************************************************************************************************************************************
#******************************************************************************************************************************************