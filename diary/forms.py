from django import forms

from .models import (Attendance, ClassRoom, Grade, Homework,
                     ScheduleItem, Subject, User)


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ['student', 'subject', 'value', 'date']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = User.objects.filter(role='student')

    def clean_value(self):
        value = self.cleaned_data['value']
        if not 2 <= value <= 5:
            raise forms.ValidationError('Оценка должна быть от 2 до 5')
        return value


class HomeworkForm(forms.ModelForm):
    class Meta:
        model = Homework
        fields = ['subject', 'class_room', 'description', 'due_date']
        widgets = {'due_date': forms.DateInput(attrs={'type': 'date'})}

    def clean_description(self):
        desc = self.cleaned_data['description']
        if len(desc.strip()) < 10:
            raise forms.ValidationError(
                'Описание должно содержать не менее 10 символов')
        return desc


class AttendanceForm(forms.ModelForm):
    class Meta:
        model = Attendance
        fields = ['student', 'subject', 'date', 'status', 'comment']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = User.objects.filter(role='student')

    def validate_unique(self):
        # Уникальность (student, subject, date) обрабатывается во view
        # через update_or_create: повторная отметка обновляет запись,
        # а не вызывает ошибку unique_together.
        pass


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = ScheduleItem
        fields = ['day', 'lesson_number', 'class_room', 'subject', 'room']

    def validate_unique(self):
        # Стандартная проверка unique_together СОХРАНЕНА намеренно:
        # при дубликате (день, урок, класс) форма покажет ошибку,
        # а не возникнет IntegrityError/500.
        super().validate_unique()


SEARCH_WIDGET = forms.TextInput(attrs={'placeholder': 'Поиск...'})


class GradeFilterForm(forms.Form):
    search = forms.CharField(required=False, label='Поиск', widget=SEARCH_WIDGET)
    student = forms.ModelChoiceField(
        queryset=User.objects.none(), required=False, empty_label='Все ученики')
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(), required=False, empty_label='Все предметы')
    date_from = forms.DateField(required=False,
                                widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False,
                              widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Queryset вычисляется в момент создания формы, а не при импорте модуля
        self.fields['student'].queryset = User.objects.filter(role='student')
        self.fields['subject'].queryset = Subject.objects.all()


class HomeworkFilterForm(forms.Form):
    search = forms.CharField(required=False, label='Поиск', widget=SEARCH_WIDGET)
    class_room = forms.ModelChoiceField(
        queryset=ClassRoom.objects.none(), required=False, empty_label='Все классы')
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(), required=False, empty_label='Все предметы')
    due_from = forms.DateField(required=False,
                               widget=forms.DateInput(attrs={'type': 'date'}))
    due_to = forms.DateField(required=False,
                             widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class_room'].queryset = ClassRoom.objects.all()
        self.fields['subject'].queryset = Subject.objects.all()


class AttendanceFilterForm(forms.Form):
    search = forms.CharField(required=False, label='Поиск', widget=SEARCH_WIDGET)
    student = forms.ModelChoiceField(
        queryset=User.objects.none(), required=False, empty_label='Все ученики')
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.none(), required=False, empty_label='Все предметы')
    status = forms.ChoiceField(
        choices=[('', 'Все статусы')] + list(Attendance.STATUS_CHOICES),
        required=False)
    date_from = forms.DateField(required=False,
                                widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False,
                              widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['student'].queryset = User.objects.filter(role='student')
        self.fields['subject'].queryset = Subject.objects.all()
