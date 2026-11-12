from django import forms

ADD_OPTION = '__add_option__'


class AddableSelect(forms.Select):
    def optgroups(self, name, value, attrs=None):
        groups = super().optgroups(name, value, attrs)
        if not (attrs or {}).get('disabled'):
            option = self.create_option(name, ADD_OPTION, '+ Нэмэх', False, len(groups))
            groups.append((None, [option], len(groups)))
        return groups


class AddableSelectMultiple(AddableSelect, forms.SelectMultiple):
    pass
