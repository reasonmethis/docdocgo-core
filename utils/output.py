class ConditionalLogger:
    def __init__(self, verbose=True):
        self.verbose = verbose

    def log(self, message):
        if self.verbose:
            print(message)

    def log_error(self, message):
        print(message)
