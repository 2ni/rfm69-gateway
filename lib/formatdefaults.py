from string import Formatter


class FormatDefaults(Formatter):
    """
    https://stackoverflow.com/questions/23407295/default-kwarg-values-for-pythons-str-format-method
    string = "{default} {somevalue}"
    fmt = FormatDefaults()
    print(fmt.format("default: {default} somevalue: {somevalue}", **{"somevalue": "xy"}))
    print(fmt.format("some value: {0}", "somevalue"))
    output: "0 xy"
    """
    def __init__(self, default_value=0):
        self.default_value = default_value
        Formatter.__init__(self)

    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            try:
                return kwargs[key]
            except KeyError:
                return self.default_value
        else:
            return Formatter.get_value(self, key, args, kwargs)
