from qt_cdse_dates import DateCatalogWorker

def test_catalog_worker_preserves_qthread_start_method():
    worker = DateCatalogWorker(None, "", "", "2023-01-01", "2023-01-02")
    assert callable(worker.start)
    assert worker.start_date == "2023-01-01"
    assert worker.end_date == "2023-01-02"
