from flask_restful import Resource,reqparse
from flask import request
from PIL import Image
import numpy as np
import tensorflow as tf
import torch
import h5py
import joblib
import json
import werkzeug
import matplotlib.pyplot as plt
from alibi.explainers import Counterfactual
from saveinfo import save_file_info
from getmodelfiles import get_model_files
import requests

class CounterfactualsImage(Resource):
    
    def post(self):
        tf.compat.v1.disable_eager_execution()
        parser = reqparse.RequestParser()
        parser.add_argument("id", required=True)
        parser.add_argument("url")
        parser.add_argument("image", type=werkzeug.datastructures.FileStorage, location='files')
        parser.add_argument('params')
        args = parser.parse_args()
        
        _id = args.get("id")
        url = args.get("url")
        image = args.get("image")
        params_json = json.loads(args.get("params"))

        output_names=None
        predic_func=None
        #Getting model info, data, and file from local repository
        model_file, model_info_file, _ = get_model_files(_id)

        ## params from info
        model_info=json.load(model_info_file)
        backend = model_info["backend"]  ##error handling?
        if "output_names" in model_info:
            output_names=model_info["output_names"]

        if model_file!=None:
            if backend=="TF1" or backend=="TF2":
                model=h5py.File(model_file, 'w')
                mlp = tf.keras.models.load_model(model)
                predic_func=mlp
            elif backend=="sklearn":
                mlp = joblib.load(model_file)
                predic_func=mlp.predict_proba
            elif backend=="PYT":
                mlp = torch.load(model_file)
                predic_func=mlp.predict
            else:
                mlp = joblib.load(model_file)
                predic_func=mlp.predict
        elif url!=None:
            def predict(X):
                return np.array(json.loads(requests.post(url, data=dict(inputs=str(X.tolist()))).text))
            predic_func=predict
        else:
            raise "Either an ID for a locally stored model or an URL for the prediction function of the model must be provided."
        
            
        if image==None:
            try:
                image = np.array(params_json["image"])
            except:
                raise "Either an image file or a matrix representative of the image must be provided."
        else:
            image = np.asarray(Image.open(image))
        if len(image.shape)<3:
            image = image.reshape(image.shape + (1,))
            plt.gray()
        image=image.reshape((1,) + image.shape)
        


        kwargsData = dict(target_proba=None,target_class='other')
        if "target_proba" in params_json:
             kwargsData["target_proba"] = params_json["target_proba"]
        if "target_class" in params_json:
             kwargsData["target_class"] = params_json["target_class"]

        cf = Counterfactual(predic_func, shape=image.shape, **{k: v for k, v in kwargsData.items() if v is not None})
        explanation = cf.explain(image)

        pred_class = explanation.cf['class']
        proba = explanation.cf['proba'][0][pred_class]       

        fig, axes = plt.subplots(1,1, figsize = (4, 4))
        axes.imshow(explanation.cf['X'][0])

        if output_names!=None:
            axes.set_title('Original Class: {}\nCounterfactual Class: {}\nProbability {:.3f}'.format(output_names[explanation.orig_class],output_names[pred_class],proba))  
        else:
            axes.set_title('Original Class: {}\nCounterfactual Class: {}\nProbability {:.3f}'.format(explanation.orig_class,pred_class,proba))  

        #saving
        upload_folder, filename, getcall = save_file_info(request.path)
        fig.savefig(upload_folder+filename+".png")

        response={"plot_png":getcall+".png","explanation":json.loads(explanation.to_json())}
        return response

    def get(self):
        return {
        "_method_description": "Displays an image that is as similar as possible to the original but with a different prediction. "
                            "This method accepts 4 arguments: " 
                           "the 'id', the 'url',  the 'params' JSON with the configuration parameters of the method, and optionally the 'image' that will be explained. "
                           "These arguments are described below.",

        "id": "Identifier of the ML model that was stored locally. If provided, then 'url' is ignored.",
        "url": "External URL of the prediction function. This url must be able to handle a POST request receiving a (multi-dimensional) array of N data points as inputs (images represented as arrays). It must return N outputs (predictions for each image).",
        "image": "Image file to be explained. Passing a file is only recommended when the model works with black and white images, or color images that are RGB-encoded using integers ranging from 0 to 255. Otherwise, pass the image in the params attribute.",
        "params": { 
                "image": "Matrix representing the image. Ignored if an image file was uploaded.",
                "target_class": "A string containing 'other' or 'same', or an integer denoting the desired class for the counterfactual instance.",
                "target_proba": "Float from 0 to 1 representing the target probability for the counterfactual generated."
                }

        }