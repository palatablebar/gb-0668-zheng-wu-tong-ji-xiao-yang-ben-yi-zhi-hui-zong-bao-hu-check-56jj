class DomainError(ValueError):
    def __init__(self, code, detail, status=422, meta=None):
        self.code, self.detail, self.status = code, detail, status
        self.meta = meta or {}
        super().__init__(detail)
