"""
ExtGen --- Python Extension module Generator.

Defines Base and Container classes.
"""

import re
import sys
import time

class BaseMetaClass(type):

    classnamespace = {}

    def __init__(cls,*args,**kws):
        n = cls.__name__
        c = BaseMetaClass.classnamespace.get(n)
        if c is None:
            BaseMetaClass.classnamespace[n] = cls
        else:
            print 'Ignoring redefinition of %s: %s defined earlier than %s' % (n, c, cls)
        type.__init__(cls, *args, **kws)

    def __getattr__(cls, name):
        try: return BaseMetaClass.classnamespace[name]
        except KeyError: pass
        raise AttributeError("'%s' object has no attribute '%s'"%
                             (cls.__name__, name))

class Base(object):

    __metaclass__ = BaseMetaClass

    container_options = dict()
    component_container_map = dict()
    template = ''

    def __new__(cls, *args, **kws):
        obj = object.__new__(cls)
        obj._args = args
        obj._provides = kws.get('provides', None)
        obj.parent = None
        obj.containers = {} # holds containers for named string lists
        obj.components = [] # holds pairs (<Base subclass instance>, <container name or None>)
        obj.initialize(*args, **kws)    # initialize from constructor arguments
        return obj

    def initialize(self, *args, **kws):
        """
        Set additional attributes, add components to instance, etc.
        """
        # self.myattr = ..
        # map(self.add, args)
        return

    @staticmethod
    def warning(message):
        print >> sys.stderr, 'extgen:',message
    @staticmethod
    def info(message):
        print >> sys.stderr, message

    def __repr__(self):
        return '%s%s' % (self.__class__.__name__, `self._args`)

    def __getattr__(self, attr):
        if attr.startswith('container_'):
            return self.get_container(attr[10:])
        raise AttributeError('%s instance has no attribute %r' % (self.__class__.__name__, attr))

    def get_container(self, key):
        """ Return named container.
        
        Rules for returning containers:
        (1) return local container if exists
        (2) return parent container if exists
        (3) create local container and return it with warning
        """
        # local container
        try:
            return self.containers[key]
        except KeyError:
            pass
        
        # parent container
        parent = self.parent
        while parent is not None:
            try:
                return parent.containers[key]
            except KeyError:
                parent = parent.parent
                continue

        # create local container
        self.warning('Created container for %r with name %r, define it in'\
                     ' .container_options mapping to get rid of this warning' \
                     % (self.__class__.__name__, key))
        c = self.containers[key] = Container()
        return c

    @property
    def provides(self):
        """
        Return a code idiom name that the current class defines.
        
        Used in avoiding redefinitions of functions and variables.
        """
        if self._provides is None:
            return '%s_%s' % (self.__class__.__name__, id(self))
        return self._provides

    def get_templates(self):
        """
        Return instance templates.
        """
        return self.template

    def generate(self):
        """
        Generate code idioms (saved in containers) and
        return evaluated template strings.
        """
        # clean up containers
        self.containers = {}
        for n in dir(self):
            if n.startswith('container_') and isinstance(getattr(self, n), Container):
                delattr(self, n)

        # create containers
        for k,kwargs in self.container_options.items():
            self.containers[k] = Container(**kwargs)

        # initialize code idioms
        self.init_containers()

        # generate component code idioms
        for component, container_key in self.components:
            old_parent = component.parent
            component.parent = self
            result = component.generate()
            if container_key is not None:
                if isinstance(container_key, tuple):
                    assert len(result)==len(container_key),`len(result),container_key`
                    results = result
                    keys = container_key
                else:
                    assert isinstance(result, str) and isinstance(container_key, str), `result, container_key`
                    results = result,
                    keys = container_key,
                for r,k in zip(results, keys):
                    container = component.get_container(k)
                    container.add(r, component.provides)
            else:
                self.warning('no label specified for component %r, ignoring its result'\
                             % (component.provides))
            component.parent = old_parent

        # update code idioms
        self.update_containers()

        # fill templates with code idioms
        templates = self.get_templates()
        if isinstance(templates, str):
            result = self.evaluate(templates)
        else:
            assert isinstance(templates, (tuple, list)),`type(templates)`
            result = tuple(map(self.evaluate, templates))
        
        return result

    def init_containers(self):
        """
        Update containers before processing components.
        """
        # container = self.get_container(<key>)
        # container.add(<string>, label=None)
        return

    def update_containers(self):
        """
        Update containers after processing components.
        """
        # container = self.get_container(<key>)
        # container.add(<string>, label=None)
        return

    def __iadd__(self, other):
        """ Convenience add.
        """
        self.add(other)
        return self

    def add(self, component, container_label=None):
        """
        Append component and its target container label to components list.
        """
        if isinstance(component, str):
            component = Base.CCode(component)
        if container_label is None:
            container_label = self.component_container_map.get(component.__class__.__name__, None)
        assert isinstance(component, Base), `type(component)`
        self.components.append((component, container_label))

    @property
    def show(self):
        # display the content of containers
        self.generate()
        r = [self.__class__.__name__]
        for k, v in self.containers.items():
            if v.list:
                r.append('--- %s ---\n%s' % (k,v))
        return '\n'.join(r)

    def evaluate(self, template, **attrs):
        """
        Evaluate template using instance attributes and code
        idioms from containers.
        """
        d = self.containers.copy()
        for n in dir(self):
            if n in ['show', 'build'] or n.startswith('_'):
                continue
            v = getattr(self, n)
            if isinstance(v, str):
                d[n] = v
        d.update(attrs)
        for label, container in self.containers.items():
            if not container.use_indent:
                continue
            replace_list = set(re.findall(r'[ ]*%\('+label+r'\)s', template))
            for s in replace_list:
                old_indent = container.indent_offset
                container.indent_offset = old_indent + len(s) - len(s.lstrip())
                i = template.index(s)
                template = template[:i] + str(container) + template[i+len(s):]
                container.indent_offset = old_indent
        template = template % d
        return re.sub(r'.*[<]KILLLINE[>].*\n','', template)

    _registered_components_map = {}

    @staticmethod
    def register(*components):
        """
        Register components so that component classes can use
        predefined components via `.get(<provides>)` method.
        """
        d = Base._registered_components_map
        for component in components:
            provides = component.provides
            if d.has_key(provides):
                Base.warning('component that provides %r is already registered, ignoring.' % (provides))
            else:
                d[provides] = component
        return

    @staticmethod
    def get(provides):
        """
        Return predefined component with given provides property..
        """
        try:
            return Base._registered_components_map[provides]
        except KeyError:
            pass
        raise KeyError('no registered component provides %r' % (provides))

    @property
    def numpy_version(self):
        import numpy
        return numpy.__version__
    
class Container(object):
    """
    Container of a list of named strings.

    >>> c = Container(separator=', ', prefix='"', suffix='"')
    >>> c.add('hey',1)
    >>> c.add('hoo',2)
    >>> print c
    "hey, hoo"
    >>> c.add('hey',1)
    >>> c.add('hey2',1)
    Traceback (most recent call last):
    ...
    ValueError: Container item 1 exists with different value

    >>> c2 = Container()
    >>> c2.add('bar')
    >>> c += c2
    >>> print c
    "hey, hoo, bar"
    
    """
    __metaclass__ = BaseMetaClass

    def __init__(self,
                 separator='\n', prefix='', suffix='',
                 skip_prefix_when_empty=False,
                 skip_suffix_when_empty=False,
                 default = '', reverse=False,
                 user_defined_str = None,
                 use_indent = False,
                 indent_offset = 0,
                 use_firstline_indent = False, # implies use_indent
                 ):
        self.list = []
        self.label_map = {}

        self.separator = separator
        self.prefix = prefix
        self.suffix = suffix
        self.skip_prefix = skip_prefix_when_empty
        self.skip_suffix = skip_suffix_when_empty
        self.default = default
        self.reverse = reverse
        self.user_str = user_defined_str
        self.use_indent = use_indent or use_firstline_indent
        self.indent_offset = indent_offset
        self.use_firstline_indent = use_firstline_indent
        
    def __notzero__(self):
        return bool(self.list)

    def has(self, label):
        return self.label_map.has_key(label)

    def get(self, label):
        return self.list[self.label_map[label]]

    def __add__(self, other):
        if isinstance(other, Container):
            lst = [(i,l) for (l,i) in other.label_map.items()]
            lst.sort()
            for i,l in lst:
                self.add(other.list[i], l)
        else:
            self.add(other)        
        return self
    __iadd__ = __add__

    def add(self, content, label=None):
        """ Add content to container using label.
        If label is None, an unique label will be generated using time.time().
        """
        if content is None:
            return
        assert isinstance(content, str),`type(content)`
        if label is None:
            label = time.time()
        if self.has(label):
            d = self.get(label)
            if d!=content:
                raise ValueError("Container item %r exists with different value" % (label))
            return
        self.list.append(content)
        self.label_map[label] = len(self.list)-1
        return

    def __str__(self):
        if self.user_str is not None:
            return self.user_str(self)
        if self.list:
            l = self.list
            if self.reverse:
                l = l[:]
                l.reverse()
            if self.use_firstline_indent:
                new_l = []
                for l1 in l:
                    lines = l1.split('\\n')
                    i = len(lines[0]) - len(lines[0].lstrip())
                    indent = i * ' '
                    new_l.append(lines[0])
                    new_l.extend([indent + l2 for l2 in lines[1:]])
                l = new_l
            r = self.separator.join(l)
            r = self.prefix + r
            r = r + self.suffix
        else:
            r = self.default
            if not self.skip_prefix:
                r = self.prefix + r
            if not self.skip_suffix:
                r = r + self.suffix
        if r and self.use_indent:
            lines = r.splitlines(True)
            indent = self.indent_offset * ' '
            r = ''.join([indent + line for line in lines])
        return r

    def copy(self, mapping=None, **extra_options):
        options = dict(separator=self.separator, prefix=self.prefix, suffix=self.suffix,
                       skip_prefix_when_empty=self.skip_prefix,
                       skip_suffix_when_empty=self.skip_suffix,
                       default = self.default, reverse=self.reverse,
                       user_defined_str = self.user_str,
                       use_indent = self.use_indent,
                       indent_offset = self.indent_offset
                       )
        options.update(extra_options)
        cpy = Container(**options)
        if mapping is None:
            cpy += self
        else:
            lst = [(i,l) for (l,i) in self.label_map.items()]
            lst.sort()
            for i,l in lst:
                cpy.add(mapping(other.list[i]), l)            
        return cpy

def _test():
    import doctest
    doctest.testmod()
    
if __name__ == "__main__":
    _test()