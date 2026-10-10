import pandas as pd
import pytest
from qt_preprocessing_core import quality_control

def test_qc_flags_duplicates_range_fraction_and_sample_count():
    frame=pd.DataFrame({'parcel_id':['A']*5,'date_start':['2023-01-01','2023-01-01','2023-01-02','2023-01-03','2023-01-04'],'ndvi_p50':[.2,.3,1.5,.5,.4],'valid_fraction_pct':[90,90,90,20,90],'sample_count':[3,3,3,3,0]})
    result,summary=quality_control(frame,50,1)
    assert result['accepted'].sum()==1
    assert 'duplicate_date' in result.loc[1,'qc_reason']
    assert 'invalid_ndvi' in result.loc[2,'qc_reason']
    assert 'low_valid_fraction' in result.loc[3,'qc_reason']
    assert 'insufficient_samples' in result.loc[4,'qc_reason']
    assert summary.iloc[0]['rejected']==4

def test_missing_required_columns():
    with pytest.raises(ValueError,match='Missing required'):
        quality_control(pd.DataFrame({'parcel_id':['A']}))

def test_optional_quality_columns_and_invalid_dates():
    frame=pd.DataFrame({'parcel_id':['A','A'],'date_start':['bad','2023-01-02'],'ndvi_p50':[.2,.5]})
    result,_=quality_control(frame)
    assert result['accepted'].sum()==1
    assert 'invalid_date' in result['qc_reason'].tolist()
