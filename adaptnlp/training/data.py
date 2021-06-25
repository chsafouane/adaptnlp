# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/15_training.data.ipynb (unless otherwise specified).

__all__ = ['ColReader', 'Categorize', 'RandomSplitter', 'TaskDatasets', 'SequenceClassificationDatasets',
           'LanguageModelDatasets']

# Cell
from transformers import AutoTokenizer, default_data_collator

from fastcore.foundation import mask2idxs, L
from fastcore.meta import delegates
from fastcore.xtras import Path, range_of
from fastai.data.core import DataLoaders

from torch.utils.data import DataLoader

import pandas as pd
from typing import Union
import os, torch
from functools import partial

from datasets import Dataset

# Cell
class ColReader:
    """
    Reads `cols` in `row` with potential `pref` and `suff`
    Based on the fastai class
    """
    def __init__(
        self,
        cols, # Some column names to use
        pref:str='', # A prefix
        suff:str='', # A suffix
        label_delim:str=None, # A label delimiter
    ):
        self.pref = str(pref) + os.path.sep if isinstance(pref, Path) else pref
        self.suff, self.label_delim = suff, label_delim
        self.cols = L(cols)

    def _do_one(self, r, c):
        o = r[c] if isinstance(c,int) else r[c] if c=='name' or c=='cat' else getattr(r,c)
        if len(self.pref)==0 and len(self.suff)==0 and self.label_delim is None: return o
        if self.label_delim is None: return f'{self.pref}{o}{self.suff}'
        else: return o.split(self.label_delim) if len(o)>0 else []

    def __call__(self, o):
        if len(self.cols) == 1: return self._do_one(o, self.cols[0])
        return L(self._do_one(o,c) for c in self.cols)

# Cell
class Categorize:
    """
    Collection of categories with reverse mapping in `o2i`
    Based on the fastai class
    """
    def __init__(
        self,
        names, # An interable collection of items to create a vocab from
        sort=True # Whether to make the items sorted
    ):
        names = L(names)
        self.classes = L(o for o in names.unique() if o == o)
        if sort: self.classes = self.classes.sorted()
        self.o2i = dict(self.classes.val2idx())

    def map_objs(
        self,
        objs # Some iterable collection
    ):
        "Map `objs` to IDs"
        return L(self.o2i[o] for o in objs)

    def map_ids(
        self,
        ids # Some ids correlating to `self.classes`
    ):
        "Map `ids` to objects in vocab"
        return L(self.classes[o] for o in ids)

    def __call__(self, o): return int(self.o2i[o])

    def decode(self, o): return self.classes[o]

# Cell
def RandomSplitter(valid_pct=0.2, seed=None):
    """
    Creates a function that splits some items between train and validation with `valid_pct` randomly
    """
    def _inner(o):
        if seed is not None: torch.manual_seed(seed)
        rand_idx = L(list(torch.randperm(len(o)).numpy()))
        cut = int(valid_pct * len(o))
        return rand_idx[cut:], rand_idx[:cut]
    return _inner

# Cell
class TaskDatasets:
    """
    A set of datasets for a particular task, with a simple API.

    Note: This is the base API, `items` should be a set of regular text and model-ready labels,
          including label or one-hot encoding being applied.
    """
    @delegates(AutoTokenizer.from_pretrained)
    def __init__(
        self,
        train_dset, # A train `Dataset` object
        valid_dset, # A validation `Dataset` object
        tokenizer_name:str = None, # The string name of a `HuggingFace` tokenizer or model. If `None`, will not tokenize the dataset.
        tokenize:bool = True, # Whether to tokenize the dataset immediatly
        **kwargs, # kwargs to go to `AutoTokenizer.from_pretrained`
    ):
        self.train = train_dset
        self.valid = valid_dset
        self.tokenizer = None
        if tokenizer_name is not None: self.set_tokenizer(tokenizer_name, **kwargs)
        if tokenize and self.tokenizer is not None: self._tokenize()
        elif tokenize and self.tokenizer is None:
            print("Tried to tokenize a dataset without a tokenizer. Please set a tokenizer with `set_tokenizer` and call `_tokenize()`")

    def __getitem__(self, idx): return self.train[idx]

    def _tokenize(self):
        "Tokenize dataset in `self.items`"
        if not self.tokenizer: raise ValueError("Tried to tokenize a dataset without a tokenizer. Please add a tokenizer with `set_tokenizer(tokenizer_name` and try again")
        def _inner(item):return self.tokenizer(item['text'], padding=True, truncation=True)
        self.train = self.train.map(_inner,batched=True,remove_columns = ['text'])
        self.valid = self.valid.map(_inner,batched=True,remove_columns = ['text'])

    @delegates(AutoTokenizer.from_pretrained)
    def set_tokenizer(
        self,
        tokenizer_name:str, # A string name of a `HuggingFace` tokenizer or model
        override_existing:bool = False, # Whether to override an existing tokenizer
        **kwargs # kwargs to go to `AutoTokenizer.from_pretrained`
    ):
        "Sets a new `AutoTokenizer` to `self.tokenizer`"
        if self.tokenizer and not override_existing:
            print(f'Warning! You are trying to override an existing tokenizer: {self.tokenizer.name_or_path}. Pass `override_existing=True` to use a new tokenizer')
            return
        elif self.tokenizer and override_existing:
            print(f'Setting new tokenizer to {tokenizer_name}')
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_name, **kwargs)
        except:
            raise ValueError(f'{tokenizer_name} is not a valid pretrained model on the HuggingFace Hub or a local model')

    @delegates(DataLoaders)
    def dataloaders(
        self,
        batch_size=8, # A batch size
        shuffle_train=True, # Whether to shuffle the training dataset
        collate_fn = default_data_collator, # A custom collation function
        **kwargs): # Torch DataLoader kwargs
        "Creates `DataLoaders` from the dataset"
        train_dl = DataLoader(self.train, shuffle=shuffle_train, collate_fn=collate_fn, batch_size=batch_size, **kwargs)
        valid_dl = DataLoader(self.valid, shuffle=False, collate_fn=collate_fn, batch_size=batch_size, **kwargs)
        return DataLoaders(train_dl, valid_dl)

# Cell
class SequenceClassificationDatasets(TaskDatasets):
    """
    A set of datasets designed for sequence classification
    """
    def __init__(
        self,
        items, # Some items we can pull x's and y's from
        get_x = ColReader('text'), # A function taking in one item and extracting the text
        get_y = ColReader('label'), # A function taking in one item and extracting the label(s)
        splits = None, # Indexs to split the data from
        tokenizer_name:str = None, # The string name of a HuggingFace tokenizer or model. If `None`, will not tokenize immediatly
        tokenize:bool=True, # Whether to tokenize the dataset immediatly
        **kwargs # kwargs to go to `AutoTokenizer.from_pretrained`
    ):
        xs = L(L(items).map(get_x)[0].values, use_list=True)
        ys = L(L(items).map(get_y)[0].values, use_list=True)
        self.categorize = Categorize(ys)
        ys = L([self.categorize(y) for y in ys], use_list=True)
        train_xs, train_ys = xs[splits[0]], ys[splits[0]]
        valid_xs, valid_ys = xs[splits[1]], ys[splits[1]]

        train_dset = Dataset.from_dict({
            'text':train_xs,
            'labels':train_ys
        })

        valid_dset = Dataset.from_dict({
            'text':valid_xs,
            'labels':valid_ys
        })

        super().__init__(train_dset, valid_dset, tokenizer_name, tokenize, **kwargs)


    @delegates(AutoTokenizer.from_pretrained)
    @classmethod
    def from_df(
        cls,
        df:pd.DataFrame, # A Pandas Dataframe or Path to a DataFrame
        text_col:str = 'text', # Name of the column the text is stored
        label_col:str = 'labels', # Name of the column the label(s) are stored
        splits = None, # Indexes to split the data with
        tokenizer_name:str = None, # The string name of a huggingFace tokenizer or model. If `None`, will not tokenize the dataset
        tokenize:bool = True, # Whether to tokenize the dataset immediatly
        **kwargs
    ):
        "Builds `SequenceClassificationDatasets` from a `DataFrame` or file path"
        get_x = ColReader(text_col)
        get_y = ColReader(label_col)
        if splits is None: splits = RandomSplitter(0.2)(range_of(df))
        return cls(df, get_x, get_y, splits, tokenizer_name, tokenize, **kwargs)

    @delegates(DataLoaders)
    def dataloaders(
        self,
        batch_size=8, # A batch size
        shuffle_train=True, # Whether to shuffle the training dataset
        collate_fn = default_data_collator, # A custom collation function
        **kwargs): # Torch DataLoader kwargs
        dls = super().dataloaders(batch_size, shuffle_train, collate_fn, **kwargs)
        dls[0].categorize = self.categorize
        return dls

# Internal Cell
def _group_texts(examples, block_size):
    # Concatenate all texts.
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
class LanguageModelDatasets(TaskDatasets):
    """
    A set of datasets designed for language model fine-tuning
    """
    def __init__(
        self,
        items, # Some items we can pull x's and y's from
        get_x = ColReader('text'), # A function taking in one item and extracting the text
        block_size:int = 512, # A block size to split up the data with
        splits = None, # Indexs to split the data from
        tokenizer_name:str = None, # The string name of a HuggingFace tokenizer or model. If `None`, will not tokenize immediatly
        tokenize:bool=True, # Whether to tokenize the dataset immediatly
        **kwargs # kwargs to go to `AutoTokenizer.from_pretrained`
    ):
        xs = L(L(items).map(get_x)[0].values, use_list=True)
        train_xs = xs[splits[0]]
        valid_xs = xs[splits[1]]

        train_dset = Dataset.from_dict({
            'text':train_xs.items
        })

        valid_dset = Dataset.from_dict({
            'text':valid_xs.items
        })

        super().__init__(train_dset, valid_dset, tokenizer_name, tokenize, **kwargs)
        self.block_size = block_size
        f = partial(_group_texts, block_size=self.block_size)
        self.train = self.train.map(f, batched=True)
        self.valid = self.valid.map(f, batched=True)

    @delegates(AutoTokenizer.from_pretrained)
    @classmethod
    def from_df(
        cls,
        df:pd.DataFrame, # A Pandas Dataframe or Path to a DataFrame
        text_col:str = 'text', # Name of the column the text is stored
        splits = None, # Indexes to split the data with
        block_size:int = 512, # A block size to split up the data with
        tokenizer_name:str = None, # The string name of a huggingFace tokenizer or model. If `None`, will not tokenize the dataset
        tokenize:bool = True, # Whether to tokenize the dataset immediatly
        **kwargs
    ):
        "Builds `SequenceClassificationDatasets` from a `DataFrame` or file path"
        get_x = ColReader(text_col)
        if splits is None: splits = RandomSplitter(0.2)(range_of(df))
        return cls(df, get_x, block_size, splits, tokenizer_name, tokenize, **kwargs)