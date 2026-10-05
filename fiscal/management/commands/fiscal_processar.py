from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from fiscal import services
from fiscal.seguranca import ErroFiscal


class Command(BaseCommand):
    help='Processa explicitamente um documento/evento fiscal como um operador autorizado.'

    def add_arguments(self,parser):
        parser.add_argument('--usuario',required=True)
        parser.add_argument('--documento',type=int)
        parser.add_argument('--evento',type=int)
        parser.add_argument('--consultar',action='store_true')

    def handle(self,**options):
        user=get_user_model().objects.get(username=options['usuario'])
        if bool(options['documento'])==bool(options['evento']):raise CommandError('Informe um documento ou evento.')
        try:
            resultado=((services.consultar_evento(user,options['evento']) if options['consultar'] else services.transmitir_evento(user,options['evento'])) if options['evento'] else
                services.consultar(user,options['documento']) if options['consultar'] else services.transmitir(user,options['documento']))
        except ErroFiscal as erro:raise CommandError(str(erro)) from None
        self.stdout.write(f'Situação fiscal: {resultado.get_status_display()}')
