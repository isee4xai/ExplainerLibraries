import matplotlib.pyplot as plt
import numpy as np
import joblib
import json
import shap
from flask_restful import Resource,reqparse
from flask import request
from saveinfo import save_file_info
from getmodelfiles import get_model_files


class ShapTreeGlobal(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder  

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("id",required=True)
        parser.add_argument('params')
        args = parser.parse_args()
        
        _id = args.get("id")
        params=args.get("params")
        params_json={}
        if(params !=None):
            params_json = json.loads(params)
        
        #getting model info, data, and file from local repository
        model_file, model_info_file, data_file = get_model_files(_id,self.model_folder)

        #getting params from request
        index=1
        if "output_index" in params_json:
            index=params_json["output_index"];


        #getting params from info
        model_info=json.load(model_info_file)
        kwargsData = dict(feature_names=None, output_names=None)
        if "feature_names" in model_info:
            kwargsData["feature_names"] = model_info["feature_names"]
        if "output_names" in model_info:
            kwargsData["output_names"] = model_info["output_names"]

        #loading model (.pkl file)
        model=joblib.load(model_file)

        #loading data
        if data_file!=None:
            dataframe = joblib.load(data_file) ##error handling?
            dataframe=dataframe.drop(dataframe.columns[len(dataframe.columns)-1], axis=1, inplace=False)
        else:
            raise Exception("The training data file was not provided.")

        #creating explanation
        explainer = shap.Explainer(model,**{k: v for k, v in kwargsData.items()})
        shap_values = explainer.shap_values(dataframe)
           
        if(len(np.array(shap_values).shape)==3): #multiclass shape: (#_of_classes, #_of_instances,#_of_features)
            shap_values=shap_values[index]

        #plotting
        plt.switch_backend('agg')
        shap.summary_plot(shap_values,features=dataframe,feature_names=explainer.feature_names,class_names=explainer.output_names)
        ##saving
        upload_folder, filename, getcall = save_file_info(request.path,self.upload_folder)
        plt.savefig(upload_folder+filename+".png",bbox_inches="tight")
       
        #formatting json output
        shap_values = [x.tolist() for x in shap_values]
        ret=json.loads(json.dumps(shap_values))
        
        #Insert code for image uploading and getting url
        response={"plot_png":getcall+".png","explanation":ret}

        return response


    def get(self):
        return {
        "_method_description": "This explaining method displays the contribution of each attribute for an individual prediction based on Shapley values (for tree ensemble methods only). Supported for XGBoost, LightGBM, CatBoost, scikit-learn and pyspark tree models. This method accepts 2 arguments: " 
                           "the 'id', and the 'params' JSON with the configuration parameters of the method. "
                           "These arguments are described below.",
        "id": "Identifier of the ML model that was stored locally.",
        "params": { 
                "output_index": "(Optional) Integer representing the index of the class to be explained. Ignore for regression models. The default index is 1.",
                }
  
        }
    

