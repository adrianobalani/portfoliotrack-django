from django.shortcuts import render, redirect
from .forms import UploadFormFile, RegisterTransactionForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from tasks.tasks import process_raw_transactions
from helpers.TransactionsFromFile import TransactionsFromFile
from .models import Transactions

from django.http import FileResponse
from django.conf import settings
import os
import datetime

# Create your views here.
@login_required(login_url='login')
def download_model_file(request):
    file_path = os.path.join(settings.STATIC_ROOT, 'media/modelo.xlsx')
    return FileResponse(open(file_path, 'rb'), as_attachment=True)

@login_required(login_url='login')
def upload_file(request):
    if request.method == 'POST':
        form = UploadFormFile(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            if file.name.endswith('.xlsx'):
                
                user_id = request.user.id
                raw_transactions_list = TransactionsFromFile().load_file(file)

                task = process_raw_transactions.delay(raw_transactions_list, user_id)
                
                messages.success(request, f'Processando transações do arquivo "{file}". Aguarde ...')
                context = {
                    'task_id': task.task_id,
                }
                
                return render(request, 'upload_file.html', context)

            else:
                messages.error(request, f"Arquivo inválido: {file}. Baixe o modelo de arquivo apropriado no menu à esquerda, botão 'Carregar de Arquivo'.")
        else:
            messages.error(request, f"Arquivo inválido: {file}. Baixe o modelo de arquivo apropriado no menu à esquerda, botão 'Carregar de Arquivo'.")
            
    return redirect('dashboard')

@login_required(login_url='login')
def register_transaction(request):
    if request.method == 'POST':
        form = RegisterTransactionForm(request.POST)
        if form.is_valid():
            transaction = [
                {
                    'date': datetime.datetime.strptime(request.POST['date'], '%Y-%m-%d'),
                    'ticker': request.POST['ticker'].upper(),
                    'operation': request.POST['operation'].upper(),
                    'quantity': int(request.POST['quantity']),
                    'unit_price': float(request.POST['unit_price']),
                    'sort_of': request.POST['sort_of'],
                }
            ]
            
            user_id = request.user.id
                        
            task = process_raw_transactions.delay(transaction, user_id)
            
            messages.success(request, f"Processando transação de {transaction[0]['operation']} de {transaction[0]['ticker']}. Aguarde ...")
            context = {
                'task_id': task.task_id,
            }
            
            return render(request, 'upload_file.html', context)
        else:
            messages.error(request, form.errors['__all__'])

    return redirect('dashboard')

@login_required(login_url='login')
def delete_transaction(request):
    if request.method == 'POST':
        strings_of_ids = request.POST.get('ids')
        if not strings_of_ids:
            messages.error(request, 'Nenhuma transação selecionada!')
            return redirect('transactions')
        list_of_ids = strings_of_ids.split(',')
        list_of_ids = [int(value) for value in list_of_ids]
        print(list_of_ids)
        print(type(list_of_ids))
        
    return redirect('transactions')

@login_required(login_url='login')
def transactions(request):
    transactions = Transactions.objects.filter(portfolio__user=request.user, operation__in=['C', 'V']).order_by('-date')
    context = {
        'transactions': transactions,
    }
    return render(request, 'transactions.html', context)
