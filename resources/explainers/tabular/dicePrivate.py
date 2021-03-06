from flask_restful import Resource,reqparse
import tensorflow as tf
import h5py
import json
import dice_ml
from html2image import Html2Image
from saveinfo import save_file_info
from getmodelfiles import get_model_files
from flask import request

class DicePrivate(Resource):

    def __init__(self,model_folder,upload_folder):
        self.model_folder = model_folder
        self.upload_folder = upload_folder
    
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("id", required=True)
        parser.add_argument('instance',required=True)
        parser.add_argument("params")

        #parsing args
        args = parser.parse_args()
        _id = args.get("id")
        instance = json.loads(args.get("instance"))
        params=args.get("params")
        params_json={}
        if(params !=None):
            params_json = json.loads(params)
        
        #Getting model info, data, and file from local repository
        model_file, model_info_file, _ = get_model_files(_id,self.model_folder)

        ## params from info
        model_info=json.load(model_info_file)
        backend = model_info["backend"]  ##error handling?
        outcome_name="Target"
        if "target_name" in model_info:
            outcome_name = model_info["target_name"]
        try:
            features = model_info["features"]
        except:
            raise Exception("The dataset \"features\" field was not specified.")

        ##converting instance to dictionary
        instance=dict(zip(features.keys(), instance))
      
        ## loading model
        if backend=="TF1" or backend=="TF2":
           model_h5=h5py.File(model_file, 'w')
           model = tf.keras.models.load_model(model_h5)
        else:
            raise Exception("Only TF1 and TF2 backends are allowed.")
        



        kwargsData = dict(features=features, outcome_name=outcome_name, type_and_precision=None, mad=None)
        if "type_and_precision" in params_json:
            kwargsData["type_and_precision"] = params_json["type_and_precision"]
        if "mad" in params_json:
            kwargsData["mad"] = params_json["mad"]

        kwargsData2 = dict(desired_class=1,total_CFs=3)
        if "num_cfs" in params_json:
           kwargsData2["total_CFs"] = params_json["num_cfs"]
        if "desired_class" in params_json:
           kwargsData2["desired_class"] = params_json["desired_class"]
        if "features_to_vary" in params_json:
           kwargsData2["features_to_vary"] = params_json["features_to_vary"]

        # Create data
        d = dice_ml.Data(**{k: v for k, v in kwargsData.items() if v is not None})
  
        # Create model
        m = dice_ml.Model(model=model, backend=backend)

        # Create CFs generator using random
        method="random"
        if "method" in params_json:
           method = params_json["method"]
        exp = dice_ml.Dice(d, m, method=method)

       
        # Generate counterfactuals
        e1 = exp.generate_counterfactuals(instance, **{k: v for k, v in kwargsData2.items() if v is not None})

        #saving
        upload_folder, filename, getcall = save_file_info(request.path,self.upload_folder)
        str_html=''
        i=1
        for cf in e1.cf_examples_list:
            if cf.final_cfs_df is None:
                cfs = "<h3>No counterfactuals were found for this instance. Perhaps try with different features.</h3>"    
           
            else:
                cfs=cf.final_cfs_df.to_html()

            str_html =  str_html + '<h2>Instance ' + str(i) + '</h2>' + cf.test_instance_df.to_html() + '<h2>Counterfactuals</h2>'+ cfs + '<br><br><hr><br>'
            i=i+1

        file = open(upload_folder+filename+".html", "w")
        file.write(str_html)
        file.close()

        hti = Html2Image()
        hti.output_path= upload_folder
        hti.screenshot(html_str=str_html, save_as=filename+".png")
        
        response={"plot_html":getcall+".html","plot_png":getcall+".png","explanation":json.loads(e1.cf_examples_list[0].final_cfs_df.to_json(orient='records'))}
        return response

    def get(self):
        return {
        "_method_description": "Generates counterfactuals without the training data. However, it requires the format and ranges of the data to be specified when uploading the model. Currently supported for TensorFlow models only.  Accepts 3 arguments: " 
                           "the 'id' string, the 'instance', and the 'params' dictionary (optional) containing the configuration parameters of the explainer."
                           " These arguments are described below.",

        "id": "Identifier of the ML model that was stored locally.",
        "instance": "Array representing a row with the feature values of an instance including the target class.",
        "params": { 

                "desired_class": "(Optional) Integer representing the index of the desired counterfactual class. Defaults to class 1. You may also use the string 'opposite' for binary classification",
                "features_to_vary": "(optional) Either a string 'all' or a list of strings representing the feature names to vary. Defaults to all features.",
                "num_cfs": "(optional) number of counterfactuals to be generated for each instance.",
                "method": "(optional) The method used for counterfactual generation. The supported methods for private data are: 'random' (random sampling) and 'genetic' (genetic algorithms). Defaults to 'random'.",
                "type_and_precision": "(optional) JSON object with continuous feature names as keys. If the feature is of type int, the value should be the string 'int'. If the feature is of type float, an array of two values is expected, containing the string 'float', and the precision.",
                "mad": "(optional) JSON with feature names as keys and corresponding Median Absolute Deviation.",
                },

        "params_example":{
            
                "features_to_vary": "all",
                "desired_class": 0,
                "num_cfs": 3,
                "method": "random",
                "type_and_precision": {"Height": ["float",1], "Weight": "int"}

               }
        }
