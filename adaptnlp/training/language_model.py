# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/14_training.language_model.ipynb (unless otherwise specified).

__all__ = ['LanguageModelDatasets', 'LanguageModelTuner']

# Cell
import pandas as pd
from fastcore.basics import mk_class
from fastcore.meta import delegates
from fastcore.xtras import Path, range_of

from fastai.basics import *
from fastai.data.core import DataLoaders
from fastai.data.transforms import get_files

from .core import *
from .arrow_utils import TextNoNewLineDatasetReader

from ..inference.text_generation import TransformersTextGenerator

from transformers import DataCollatorForLanguageModeling, default_data_collator
from datasets import Dataset

from typing import List

# Internal Cell
def _group_texts(examples, block_size):
    # Concatenate all texts, based on code by Transformers
    concatenated_examples = {k: sum(examples[k], []) for k in examples.keys()}
    total_length = len(concatenated_examples[list(examples.keys())[0]])
    # We drop the small remainder, we could add padding if the model supported it instead of this drop, you can
    # customize this part to your needs.
    total_length = (total_length // block_size) * block_size
    # Split by chunks of max_len.
    result = {
        k: [t[i : i + block_size] for i in range(0, total_length, block_size)]
        for k, t in concatenated_examples.items()
    }
    result["labels"] = result["input_ids"].copy()
    return result

# Cell
def _tokenize(item, tokenizer, tokenize_kwargs): return tokenizer(item['text'], **tokenize_kwargs)

# Cell
class LanguageModelDatasets(TaskDatasets):
    """
    A set of datasets designed for language model fine-tuning
    """
    def __init__(
        self,
        train_dset,
        valid_dset,
        tokenizer_name,
        tokenize,
        tokenize_kwargs,
        auto_kwargs,
        remove_columns,
        block_size,
        masked_lm
    ):
        "Constructs TaskDatasets, should not be called explicitly"
        super().__init__(
            train_dset,
            valid_dset,
            tokenizer_name,
            tokenize,
            _tokenize,
            tokenize_kwargs,
            auto_kwargs
        )
        self.masked_lm = masked_lm
        self.block_size = block_size
        f = partial(_group_texts, block_size=self.block_size)
        self.train = self.train.map(f, batched=True)
        self.valid = self.valid.map(f, batched=True)

    @classmethod
    def from_dfs(
        cls,
        train_df:pd.DataFrame, # A Pandas Dataframe
        text_col:str, # The name of the text column
        tokenizer_name:str, # The name of the tokenizer
        block_size:int=128, # The size of each block
        masked_lm:bool=False, # Whether the language model is a MLM
        valid_df:pd.DataFrame=None, # An optional validation DataFrame
        split_func:callable=None, # Optionally a splitting function similar to RandomSplitter
        split_pct:float=.1, # What % to split the df between training and validation
        tokenize_kwargs:dict={}, # kwargs for the tokenize function
        auto_kwargs:dict={} # kwargs for the AutoTokenizer.from_pretrained constructor
    ):
        "Builds `LanguageModelDatasets` from a `DataFrame` or file path"
        if split_func is None: split_func = RandomSplitter(split_pct)
        if valid_df is None:
            train_idxs, valid_idxs = split_func(range_of(train_df))
            valid_df = train_df.iloc[valid_idxs]
            train_df = train_df.iloc[train_idxs]

        train_df = train_df[[text_col]]
        valid_df = valid_df[[text_col]]

        train_df = train_df.rename(columns={text_col:'text'})
        valid_df = valid_df.rename(columns={text_col:'text'})

        train_dset = Dataset.from_dict(train_df.to_dict('list'))
        valid_dset = Dataset.from_dict(valid_df.to_dict('list'))

        dsets = TaskDatasets(
            train_dset,
            valid_dset,
            tokenizer_name,
            False,
            _tokenize,
            tokenize_kwargs=tokenize_kwargs,
            auto_kwargs=auto_kwargs
        )

        f = partial(_group_texts, block_size=512)
        t = partial(_tokenize, tokenizer=dsets.tokenizer, tokenize_kwargs=tokenize_kwargs)
        dsets.train = dsets.train.map(t, batched=True, remove_columns=['text'])
        dsets.valid = dsets.valid.map(t, batched=True, remove_columns=['text'])

        dsets.train = dsets.train.map(f, batched=True)
        dsets.valid = dsets.valid.map(f, batched=True)
        return dsets

    @classmethod
    def from_csvs(
        cls,
        train_csv:Path, # A training csv file
        text_col:str, # The name of the text column
        tokenizer_name:str, # The name of the tokenizer
        block_size:int=128, # The size of each block
        masked_lm:bool=False, # Whether the language model is a MLM
        valid_csv:Path=None, # An optional validation csv
        split_func:callable=None, # Optionally a splitting function similar to RandomSplitter
        split_pct:float=.1, # What % to split the df between training and validation
        tokenize_kwargs:dict={}, # kwargs for the tokenize function
        auto_kwargs:dict={}, # kwargs for the AutoTokenizer.from_pretrained constructor
        **kwargs, # kwargs for `pd.read_csv`
    ):
        "Builds `LanguageModelDatasets` from a single csv or set of csvs. A convience constructor for `from_dfs`"
        train_df = pd.read_csv(train_csv, **kwargs)
        if valid_csv is not None: valid_df = pd.read_csv(valid_csv, **kwargs)
        else: valid_df = None
        return cls.from_dfs(
            train_df,
            text_col,
            tokenizer_name,
            block_size,
            masked_lm,
            valid_df,
            split_func,
            split_pct,
            tokenize_kwargs,
            auto_kwargs
        )

    @classmethod
    def from_folders(
        cls,
        train_path:Path, # The path to the training data
        tokenizer_name:str, # The name of the tokenizer
        block_size:int=128, # The size of each block
        masked_lm:bool=False, # Whether the language model is a MLM
        valid_path:Path=None, # An optional validation path
        split_func:callable=None, # Optionally a splitting function similar to RandomSplitter
        split_pct:float=.1, # What % to split the df between training and validation
        tokenize_kwargs:dict={}, # kwargs for the tokenize function
        auto_kwargs:dict={} # kwargs for the AutoTokenizer.from_pretrained constructor
    ):
        "Builds `LanguageModelDatasets` from a folder or group of folders"
        train_txts = get_files(train_path, extensions='.txt')
        if valid_path is not None:
            valid_txts = get_files(valid_path, extensions='.txt')
        else:
            if split_func is not None:
                split_func = RandomSplitter(split_pct)
            train_idxs, valid_idxs = split_func(train_txts)
            valid_txts = train_txts[valid_idxs]
            train_txts = train_txts[train_idxs]
        train_txts = [str(x) for x in train_txts]
        valid_txts = [str(x) for x in valid_txts]
        train_dset = TextNoNewLineDatasetReader(train_txts).read()
        valid_dset = TextNoNewLineDatasetReader(valid_txts).read()

        dsets = TaskDatasets(
            train_dset,
            valid_dset,
            tokenizer_name,
            False,
            _tokenize,
            tokenize_kwargs=tokenize_kwargs,
            auto_kwargs=auto_kwargs
        )

        f = partial(_group_texts, block_size=512)
        t = partial(_tokenize, tokenizer=dsets.tokenizer, tokenize_kwargs=tokenize_kwargs)
        dsets.train = dsets.train.map(t, batched=True, remove_columns=['text'])
        dsets.valid = dsets.valid.map(t, batched=True, remove_columns=['text'])

        dsets.train = dsets.train.map(f, batched=True)
        dsets.valid = dsets.valid.map(f, batched=True)
        return dsets

    @delegates(DataLoaders)
    def dataloaders(
        self,
        batch_size=8, # A batch size
        shuffle_train=True, # Whether to shuffle the training dataset
        collate_fn = default_data_collator, # A custom collation function
        mlm_probability:float = 0.15, # Token masking probablity for Masked Language Models
        **kwargs
    ):
        "Build DataLoaders from `self`"
        if self.masked_lm: collate_fn = DataCollatorForLanguageModeling(tokenizer=self.tokenizer, mlm_probability=mlm_probability)
        return super().dataloaders(batch_size, shuffle_train, collate_fn, **kwargs)

# Cell
from transformers import AutoModelForMaskedLM, AutoModelForCausalLM, AutoModelForSeq2SeqLM

mk_class('LMType', **{o:o.lower() for o in ['Masked', 'Causal', 'Seq2Seq']},
        doc="All valid language model classes with typo-proofing")

_constructors = {
    'masked':AutoModelForMaskedLM.from_pretrained,
    'causal':AutoModelForCausalLM.from_pretrained,
    'seq2seq':AutoModelForSeq2SeqLM.from_pretrained
}

# Cell
class LanguageModelTuner(AdaptiveTuner):
    """
    An `AdaptiveTuner` with good defaults for Language Model fine-tuning
    **Valid kwargs and defaults:**
      - `lr`:float = 0.001
      - `splitter`:function = `trainable_params`
      - `cbs`:list = None
      - `path`:Path = None
      - `model_dir`:Path = 'models'
      - `wd`:float = None
      - `wd_bn_bias`:bool = False
      - `train_bn`:bool = True
      - `moms`: tuple(float) = (0.95, 0.85, 0.95)
    """
    def __init__(
        self,
        dls:DataLoaders, # A set of DataLoaders or AdaptiveDataLoaders
        model_name, # A HuggingFace model
        tokenizer = None, # A HuggingFace tokenizer
        language_model_type:LMType = LMType.Causal, # The type of language model to use
        loss_func = CrossEntropyLossFlat(), # A loss function
        metrics = [Perplexity()], # Metrics to monitor the training with
        opt_func = Adam, # A fastai or torch Optimizer
        additional_cbs = None, # Additional Callbacks to have always tied to the Tuner,
        expose_fastai_api = False, # Whether to expose the fastai API
        **kwargs, # kwargs for `Learner.__init__`
    ):
        additional_cbs = listify(additional_cbs)
        for arg in 'dls,model,loss_func,metrics,opt_func,cbs,expose_fastai'.split(','):
            if arg in kwargs.keys(): kwargs.pop(arg) # Pop all existing kwargs

        if language_model_type is None: raise ValueError("Please specify the type of language model you want to use, such as `masked` or `causal`")
        if language_model_type not in _constructors.keys():
            raise ValueError(
                """
                Please enter a valid Langauge Model Type of:
                  * `masked` or `LMType.Masked`
                  * `causal` or `LMType.Causal`
                  * `seq2seq` or `LMType.Seq2Seq`
                """
            )
        try:
            model = _constructors[language_model_type](model_name)
        except Exception as e:
            message = e.args[0]
            m = f"Was not able to create a {language_model_type} instance of {model_name}. Please use a valid model for your task:"
            m += message
            e.args = [m]
            raise e

        if tokenizer is None: tokenizer = AutoTokenizer.from_pretrained(model_name)
        tokenizer.pad_token = "<PAD>"

        super().__init__(
            expose_fastai_api,
            dls = dls,
            model = model,
            tokenizer = tokenizer,
            loss_func = loss_func,
            metrics = metrics,
            opt_func = opt_func,
            cbs=additional_cbs,
            **kwargs
        )

    def predict(
        self,
        text:Union[List[str], str], # Some text or list of texts to do inference with
        bs:int=64, # A batch size to use for multiple texts
        num_tokens_to_produce:int=50, # Number of tokens to generate
        **kwargs, # Optional arguments for `PretrainedModel.generate`
    ):
        "Predict some `text` for sequence classification with the currently loaded model"
        if getattr(self, '_inferencer', None) is None:

            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token="<PAD>"
            self._inferencer = TransformersTextGenerator(self.tokenizer,self.model)
        return self._inferencer.predict(text, bs, num_tokens_to_produce, **kwargs)