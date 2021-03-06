from flask_restful import Resource,reqparse
import tensorflow as tf
import torch
import numpy as np
import joblib
import h5py
import json
import shap
from flask import request
import matplotlib.pyplot as plt
from saveinfo import save_file_info
from getmodelfiles import get_model_files
import requests

class ShapKernelLocal(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder
        
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('id',required=True)
        parser.add_argument('instance',required=True)
        parser.add_argument('url')
        parser.add_argument('params')
        args = parser.parse_args()
        
        _id = args.get("id")
        instance = json.loads(args.get("instance"))
        url = args.get("url")
        params=args.get("params")
        params_json={}
        if(params !=None):
            params_json = json.loads(params)
        
        
        #Getting model info, data, and file from local repository
        model_file, model_info_file, data_file = get_model_files(_id,self.model_folder)

        ## loading data
        if data_file!=None:
            dataframe = joblib.load(data_file) ##error handling?
        else:
            raise Exception("The training data file was not provided.")

        #getting params from request
        index=1
        plot_type=None
        if "output_index" in params_json:
            index=params_json["output_index"]
        if "plot_type" in params_json:
            plot_type=params_json["plot_type"];

        ##getting params from info
        model_info=json.load(model_info_file)
        backend = model_info["backend"]  ##error handling?

        kwargsData = dict(feature_names=None, output_names=None)
        if "feature_names" in model_info:
            kwargsData["feature_names"] = model_info["feature_names"]
        else:
            kwargsData["feature_names"]=["Feature "+str(i) for i in range(len(instance))]
        if "output_names" in model_info:
            kwargsData["output_names"] = model_info["output_names"]


        ## getting predict function
        predic_func=None
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
            raise Exception("Either a stored model or a valid URL for the prediction function must be provided.")


        # Create data
        explainer = shap.KernelExplainer(predic_func, dataframe.drop(dataframe.columns[len(dataframe.columns)-1], axis=1, inplace=False),**{k: v for k, v in kwargsData.items()})

        shap_values = explainer.shap_values(np.array(instance))
        
        if(len(np.array(shap_values).shape)!=1):
            explainer.expected_value=explainer.expected_value[index]
            shap_values=shap_values[index]
            
        #plotting
        plt.switch_backend('agg')
        if plot_type=="bar":
            shap.plots._bar.bar_legacy(shap_values,features=np.array(instance),feature_names=kwargsData["feature_names"],show=False)
        elif plot_type=="decision":
            shap.decision_plot(explainer.expected_value,shap_values=shap_values,features=np.array(instance),feature_names=kwargsData["feature_names"])
        elif plot_type=="force":
                shap.plots._force.force(explainer.expected_value,shap_values=shap_values,features=np.array(instance),feature_names=kwargsData["feature_names"],out_names=kwargsData["output_names"],matplotlib=True,show=False)
        else:
            if plot_type==None:
                print("No plot type was specified. Defaulting to waterfall plot.")
            elif plot_type!="waterfall":
                print("No plot with the specified name was found. Defaulting to waterfall plot.")
            shap.plots._waterfall.waterfall_legacy(explainer.expected_value,shap_values=shap_values,features=np.array(instance),feature_names=kwargsData["feature_names"],show=False)
       
        #saving force plot to html (DEPRECATED)
        #additive_exp = shap.force_plot(explainer.expected_value, shap_values,features=np.array(instance),feature_names=kwargsData["feature_names"],out_names=out_names,show=False)
        
        ##saving
        upload_folder, filename, getcall = save_file_info(request.path,self.upload_folder)
        plt.savefig(upload_folder+filename+".png",bbox_inches="tight")
        #shap.plots._force.save_html(upload_folder+filename+".html",additive_exp)
        
        #formatting json output
        shap_values = [x.tolist() for x in shap_values]
        ret=json.loads(json.dumps(shap_values))
        
        #Insert code for image uploading and getting url
        response={"plot_png":getcall+".png","explanation":ret}

        return response


    def get(self):
        return {
        "_method_description": "This explaining method displays the contribution of each attribute for an individual prediction based on Shapley values. This method accepts 4 arguments: " 
                           "the 'id', the 'instance', the 'url' (optional),  and the 'params' dictionary (optional) with the configuration parameters of the method. "
                           "These arguments are described below.",
        "id": "Identifier of the ML model that was stored locally.",
        "instance": "Array with the feature values of an instance without including the target class.",
        "url": "External URL of the prediction function. Ignored if a model file was uploaded to the server. "
               "This url must be able to handle a POST request receiving a (multi-dimensional) array of N data points as inputs (instances represented as arrays). It must return a array of N outputs (predictions for each instance).",
        "params": { 
                "output_index": "(Optional) Integer representing the index of the class to be explained. Ignore for regression models. The default index is 1." 
                }
        }
    

